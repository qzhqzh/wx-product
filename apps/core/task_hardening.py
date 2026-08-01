from datetime import timedelta
from types import MethodType

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.assets.models import AssetVersion
from apps.assets.services import assemble_gif, create_asset, normalize_static_asset, transform_frame
from apps.emoji.models import (
    AnimationFrame,
    AnimationSequence,
    EmojiItem,
    EmojiPack,
    GenerationJob,
)
from apps.emoji.pipeline import transition_pack
from apps.integrations.providers import (
    ProviderCapabilityError,
    ProviderConfigurationError,
    get_provider,
)

from .pipeline import transition_project

_INSTALLED = False


def _running_lease_seconds() -> int:
    return int(getattr(settings, "CELERY_TASK_TIME_LIMIT", 15 * 60)) + 60


def _claim_job(job_id) -> int | None:
    now = timezone.now()
    stale_before = now - timedelta(seconds=_running_lease_seconds())
    with transaction.atomic():
        job = GenerationJob.objects.select_for_update().get(pk=job_id)
        if job.status in {
            GenerationJob.Status.SUCCEEDED,
            GenerationJob.Status.CANCELLED,
        }:
            return None
        if (
            job.status == GenerationJob.Status.RUNNING
            and job.started_at
            and job.started_at > stale_before
        ):
            return None
        job.status = GenerationJob.Status.RUNNING
        job.started_at = now
        job.completed_at = None
        job.attempts += 1
        job.error_code = ""
        job.error_message = ""
        job.save(
            update_fields=[
                "status",
                "started_at",
                "completed_at",
                "attempts",
                "error_code",
                "error_message",
                "updated_at",
            ]
        )
        return job.attempts


def _finish(job_id, attempt: int, **updates) -> bool:
    updates["updated_at"] = timezone.now()
    return bool(
        GenerationJob.objects.filter(
            pk=job_id,
            status=GenerationJob.Status.RUNNING,
            attempts=attempt,
        ).update(**updates)
    )


def _succeed(job_id, attempt: int, payload: dict, model: str) -> None:
    _finish(
        job_id,
        attempt,
        status=GenerationJob.Status.SUCCEEDED,
        output_payload=payload,
        model=model,
        completed_at=timezone.now(),
    )


def _block(job_id, attempt: int, message: str) -> None:
    _finish(
        job_id,
        attempt,
        status=GenerationJob.Status.BLOCKED,
        error_code="provider_configuration",
        error_message=message,
        completed_at=timezone.now(),
    )


def _fail(job_id, attempt: int, exc: Exception, job_type: str) -> None:
    _finish(
        job_id,
        attempt,
        status=GenerationJob.Status.FAILED,
        error_code=exc.__class__.__name__,
        error_message=str(exc),
        completed_at=timezone.now(),
        output_payload={"safe_error": str(exc), "task": job_type},
    )


def _existing_output(job_id):
    return (
        GenerationJob.objects.filter(pk=job_id)
        .values_list("output_payload", flat=True)
        .first()
        or {}
    )


def plan_pack_run(self, job_id):
    attempt = _claim_job(job_id)
    if attempt is None:
        return _existing_output(job_id)
    job = GenerationJob.objects.select_related("pack").get(pk=job_id)
    try:
        provider = get_provider(job.provider, capability="text")
        pack = job.pack
        plan = provider.plan_pack(
            name=pack.name,
            brief=pack.creative_brief,
            tone=pack.tone,
            count=pack.target_count,
        )
        with transaction.atomic():
            for order, item_data in enumerate(plan.items, start=1):
                EmojiItem.objects.update_or_create(
                    pack=pack,
                    order=order,
                    defaults={
                        "meaning": item_data.meaning,
                        "copy_text": item_data.copy_text,
                        "action": item_data.action,
                        "prompt": item_data.prompt,
                    },
                )
            pack.description = pack.description or plan.summary
            pack.save(update_fields=["description", "updated_at"])
        pack.refresh_from_db()
        if pack.status in {EmojiPack.Status.BRIEF_APPROVED, EmojiPack.Status.REWORK}:
            transition_pack(
                pack,
                EmojiPack.Status.GENERATING,
                actor=job.created_by,
                note="语义策划完成，进入素材生成",
            )
        _succeed(
            job.pk,
            attempt,
            {"item_count": len(plan.items), "summary": plan.summary},
            provider.text_model,
        )
    except (ProviderConfigurationError, ProviderCapabilityError) as exc:
        _block(job.pk, attempt, str(exc))
    except Exception as exc:
        _fail(job.pk, attempt, exc, job.job_type)
        raise


def generate_item_run(self, job_id):
    attempt = _claim_job(job_id)
    if attempt is None:
        return _existing_output(job_id)
    job = GenerationJob.objects.select_related("pack", "item").get(pk=job_id)
    try:
        provider = get_provider(job.provider, capability="image")
        item = job.item
        reference = None
        character = item.pack.project.character_version
        if character:
            reference_asset = (
                AssetVersion.objects.filter(
                    metadata__character_version_id=str(character.pk),
                    kind=AssetVersion.Kind.REFERENCE,
                )
                .order_by("-created_at")
                .first()
            )
            if reference_asset:
                from apps.assets.services import read_asset

                reference = read_asset(reference_asset)
        generated = provider.generate_image(
            prompt=job.prompt,
            meaning=item.meaning,
            order=item.order - 1,
            reference=reference,
            negative_prompt=job.input_payload.get("negative_prompt", ""),
        )
        raw_asset = create_asset(
            content=generated.content,
            filename=generated.filename,
            kind=AssetVersion.Kind.CANDIDATE,
            source=(
                AssetVersion.Source.OPENAI
                if job.provider == "openai"
                else AssetVersion.Source.LOCAL
            ),
            actor=job.created_by,
            mime_type=generated.mime_type,
            metadata=generated.metadata,
        )
        final_asset = normalize_static_asset(raw_asset, actor=job.created_by)
        item.candidates.add(raw_asset, final_asset)
        if not item.selected_asset_id:
            item.selected_asset = final_asset
            item.save(update_fields=["selected_asset", "updated_at"])
        pack = EmojiPack.objects.get(pk=item.pack_id)
        if (
            pack.status == EmojiPack.Status.GENERATING
            and pack.items.exclude(selected_asset=None).count() >= pack.target_count
        ):
            transition_pack(
                pack,
                EmojiPack.Status.CREATIVE_REVIEW,
                actor=job.created_by,
                note="全部目标素材已生成",
            )
        _succeed(
            job.pk,
            attempt,
            {"raw_asset_id": str(raw_asset.pk), "asset_id": str(final_asset.pk)},
            provider.image_model,
        )
    except (ProviderConfigurationError, ProviderCapabilityError) as exc:
        _block(job.pk, attempt, str(exc))
    except Exception as exc:
        _fail(job.pk, attempt, exc, job.job_type)
        raise


def optimize_prompt_run(self, job_id):
    attempt = _claim_job(job_id)
    if attempt is None:
        return _existing_output(job_id)
    job = GenerationJob.objects.select_related("pack", "item").get(pk=job_id)
    try:
        provider = get_provider(job.provider, capability="text")
        item = job.item
        optimized = provider.optimize_prompt(
            prompt=job.prompt,
            meaning=item.meaning,
            action=item.action,
            tone=item.pack.tone,
            negative_prompt=job.input_payload.get("negative_prompt", ""),
        )
        item.prompt = optimized
        item.save(update_fields=["prompt", "updated_at"])
        _succeed(job.pk, attempt, {"prompt": optimized}, provider.text_model)
    except (ProviderConfigurationError, ProviderCapabilityError) as exc:
        _block(job.pk, attempt, str(exc))
    except Exception as exc:
        _fail(job.pk, attempt, exc, job.job_type)
        raise


def generate_frames_run(self, job_id):
    attempt = _claim_job(job_id)
    if attempt is None:
        return _existing_output(job_id)
    job = GenerationJob.objects.select_related("pack", "item__selected_asset").get(pk=job_id)
    try:
        item = job.item
        if not item.selected_asset_id:
            raise ValueError("请先为表情选择一张静态母图。")
        frame_count = max(2, min(int(job.input_payload.get("frame_count", 6)), 12))
        generated_assets = [
            transform_frame(
                item.selected_asset,
                frame_index=index,
                total_frames=frame_count,
                actor=job.created_by,
            )
            for index in range(frame_count)
        ]
        with transaction.atomic():
            locked_item = EmojiItem.objects.select_for_update().get(pk=item.pk)
            sequence, _ = AnimationSequence.objects.get_or_create(item=locked_item)
            sequence.frames.all().delete()
            AnimationFrame.objects.bulk_create(
                [
                    AnimationFrame(
                        sequence=sequence,
                        order=index + 1,
                        duration_ms=120,
                        asset=asset,
                    )
                    for index, asset in enumerate(generated_assets)
                ]
            )
            output = assemble_gif(sequence, actor=job.created_by)
        _succeed(
            job.pk,
            attempt,
            {
                "frame_count": frame_count,
                "sequence_id": str(sequence.pk),
                "asset_id": str(output.pk),
            },
            "pillow-sequence-v1",
        )
    except Exception as exc:
        _fail(job.pk, attempt, exc, job.job_type)
        raise


def assemble_sequence_run(self, job_id):
    attempt = _claim_job(job_id)
    if attempt is None:
        return _existing_output(job_id)
    job = GenerationJob.objects.select_related("item__animation_sequence").get(pk=job_id)
    try:
        with transaction.atomic():
            sequence = AnimationSequence.objects.select_for_update().get(
                pk=job.item.animation_sequence.pk
            )
            output = assemble_gif(sequence, actor=job.created_by)
            frame_count = sequence.frames.count()
        _succeed(
            job.pk,
            attempt,
            {
                "frame_count": frame_count,
                "sequence_id": str(sequence.pk),
                "asset_id": str(output.pk),
            },
            "pillow-sequence-v1",
        )
    except Exception as exc:
        _fail(job.pk, attempt, exc, job.job_type)
        raise


def expire_trend_projects_run(self):
    from apps.core.models import CreativeProject

    project_ids = list(
        CreativeProject.objects.filter(
            status=CreativeProject.Status.ACTIVE,
            trend_topic__expires_at__lte=timezone.now(),
        ).values_list("pk", flat=True)
    )
    transitioned = 0
    for project_id in project_ids:
        project = CreativeProject.objects.filter(pk=project_id).first()
        if project is None:
            continue
        try:
            transition_project(
                project,
                CreativeProject.Status.PAUSED,
                action="trend_expired",
                note="关联热点已过期，系统自动暂停项目",
                payload={"trend_topic_id": str(project.trend_topic_id)},
            )
            transitioned += 1
        except ValueError:
            continue
    return transitioned


def install_task_hardening() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    from apps.emoji import tasks

    replacements = {
        "plan_pack_task": plan_pack_run,
        "generate_item_task": generate_item_run,
        "optimize_item_prompt_task": optimize_prompt_run,
        "generate_frames_task": generate_frames_run,
        "assemble_sequence_task": assemble_sequence_run,
        "expire_trend_projects": expire_trend_projects_run,
    }
    for task_name, implementation in replacements.items():
        task = getattr(tasks, task_name)
        concrete_task = (
            task._get_current_object()
            if hasattr(task, "_get_current_object")
            else task
        )
        concrete_task.run = MethodType(implementation, concrete_task)
    _INSTALLED = True
