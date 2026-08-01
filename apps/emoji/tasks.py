import hashlib

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.assets.models import AssetVersion
from apps.assets.services import (
    assemble_gif,
    create_asset,
    normalize_static_asset,
    transform_frame,
)
from apps.integrations.providers import (
    ProviderCapabilityError,
    ProviderConfigurationError,
    get_provider,
)

from .models import (
    AnimationFrame,
    AnimationSequence,
    EmojiItem,
    EmojiPack,
    GenerationJob,
)
from .prompts import compose_item_prompt


def make_idempotency_key(*parts) -> str:
    raw = ":".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode()).hexdigest()


def enqueue_plan_job(pack, *, provider, actor=None, dispatch=True):
    key = make_idempotency_key("plan", pack.pk, provider, pack.target_count, pack.updated_at)
    job, created = GenerationJob.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "pack": pack,
            "job_type": GenerationJob.JobType.PLAN,
            "provider": provider,
            "created_by": actor,
            "input_payload": {"target_count": pack.target_count},
        },
    )
    if dispatch and (
        created or job.status in {GenerationJob.Status.FAILED, GenerationJob.Status.BLOCKED}
    ):
        plan_pack_task.delay(str(job.pk))
    return job


def enqueue_image_job(item, *, provider, actor=None, dispatch=True):
    prompt, negative_prompt, preset_ids = compose_item_prompt(item)
    key = make_idempotency_key("image", item.pk, provider, prompt, negative_prompt)
    job, created = GenerationJob.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "pack": item.pack,
            "item": item,
            "job_type": GenerationJob.JobType.IMAGE,
            "provider": provider,
            "prompt": prompt,
            "created_by": actor,
            "input_payload": {
                "negative_prompt": negative_prompt,
                "prompt_preset_ids": preset_ids,
            },
        },
    )
    if dispatch and (
        created or job.status in {GenerationJob.Status.FAILED, GenerationJob.Status.BLOCKED}
    ):
        generate_item_task.delay(str(job.pk))
    return job


def enqueue_prompt_job(item, *, provider, actor=None, dispatch=True):
    _, negative_prompt, preset_ids = compose_item_prompt(item)
    key = make_idempotency_key("prompt", item.pk, provider, item.prompt, negative_prompt)
    job, created = GenerationJob.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "pack": item.pack,
            "item": item,
            "job_type": GenerationJob.JobType.PROMPT,
            "provider": provider,
            "prompt": item.prompt,
            "created_by": actor,
            "input_payload": {
                "negative_prompt": negative_prompt,
                "prompt_preset_ids": preset_ids,
            },
        },
    )
    if dispatch and (
        created or job.status in {GenerationJob.Status.FAILED, GenerationJob.Status.BLOCKED}
    ):
        optimize_item_prompt_task.delay(str(job.pk))
    return job


def enqueue_frames_job(item, *, frame_count=6, actor=None):
    key = make_idempotency_key(
        "frames", item.pk, item.selected_asset_id, frame_count, item.updated_at
    )
    job, created = GenerationJob.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "pack": item.pack,
            "item": item,
            "job_type": GenerationJob.JobType.FRAME,
            "provider": "sequence",
            "created_by": actor,
            "input_payload": {"frame_count": frame_count},
        },
    )
    if created or job.status == GenerationJob.Status.FAILED:
        generate_frames_task.delay(str(job.pk))
    return job


def enqueue_assemble_job(sequence, *, actor=None):
    frame_signature = [
        (str(frame.pk), frame.order, frame.duration_ms)
        for frame in sequence.frames.order_by("order")
    ]
    key = make_idempotency_key(
        "assemble",
        sequence.pk,
        sequence.loop_count,
        frame_signature,
    )
    job, created = GenerationJob.objects.get_or_create(
        idempotency_key=key,
        defaults={
            "pack": sequence.item.pack,
            "item": sequence.item,
            "job_type": GenerationJob.JobType.ASSEMBLE,
            "provider": "sequence",
            "created_by": actor,
            "input_payload": {"sequence_id": str(sequence.pk)},
        },
    )
    if created or job.status == GenerationJob.Status.FAILED:
        assemble_sequence_task.delay(str(job.pk))
    return job


@shared_task(bind=True, autoretry_for=(), max_retries=0)
def plan_pack_task(self, job_id):
    job = GenerationJob.objects.select_related("pack").get(pk=job_id)
    _start(job)
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
            pack.status = EmojiPack.Status.GENERATING
            pack.description = pack.description or plan.summary
            pack.save(update_fields=["status", "description", "updated_at"])
        _succeed(job, {"item_count": len(plan.items), "summary": plan.summary}, provider.text_model)
    except (ProviderConfigurationError, ProviderCapabilityError) as exc:
        _block(job, str(exc))
    except Exception as exc:
        _fail(job, exc)
        raise


@shared_task(bind=True, autoretry_for=(), max_retries=0)
def generate_item_task(self, job_id):
    job = GenerationJob.objects.select_related("pack", "item").get(pk=job_id)
    _start(job)
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
        pack = item.pack
        if (
            pack.status == EmojiPack.Status.GENERATING
            and pack.items.exclude(selected_asset=None).count() >= pack.target_count
        ):
            pack.status = EmojiPack.Status.CREATIVE_REVIEW
            pack.save(update_fields=["status", "updated_at"])
        _succeed(
            job,
            {"raw_asset_id": str(raw_asset.pk), "asset_id": str(final_asset.pk)},
            provider.image_model,
        )
    except (ProviderConfigurationError, ProviderCapabilityError) as exc:
        _block(job, str(exc))
    except Exception as exc:
        _fail(job, exc)
        raise


@shared_task(bind=True, autoretry_for=(), max_retries=0)
def optimize_item_prompt_task(self, job_id):
    job = GenerationJob.objects.select_related("pack", "item").get(pk=job_id)
    _start(job)
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
        _succeed(job, {"prompt": optimized}, provider.text_model)
    except (ProviderConfigurationError, ProviderCapabilityError) as exc:
        _block(job, str(exc))
    except Exception as exc:
        _fail(job, exc)
        raise


@shared_task(bind=True, autoretry_for=(), max_retries=0)
def generate_frames_task(self, job_id):
    job = GenerationJob.objects.select_related("pack", "item__selected_asset").get(pk=job_id)
    _start(job)
    try:
        item = job.item
        if not item.selected_asset_id:
            raise ValueError("请先为表情选择一张静态母图。")
        frame_count = max(2, min(int(job.input_payload.get("frame_count", 6)), 12))
        sequence, _ = AnimationSequence.objects.get_or_create(item=item)
        sequence.frames.all().delete()
        for index in range(frame_count):
            asset = transform_frame(
                item.selected_asset,
                frame_index=index,
                total_frames=frame_count,
                actor=job.created_by,
            )
            AnimationFrame.objects.create(
                sequence=sequence,
                order=index + 1,
                duration_ms=120,
                asset=asset,
            )
        output = assemble_gif(sequence, actor=job.created_by)
        _succeed(
            job,
            {
                "frame_count": frame_count,
                "sequence_id": str(sequence.pk),
                "asset_id": str(output.pk),
            },
            "pillow-sequence-v1",
        )
    except Exception as exc:
        _fail(job, exc)
        raise


@shared_task(bind=True, autoretry_for=(), max_retries=0)
def assemble_sequence_task(self, job_id):
    job = GenerationJob.objects.select_related("item__animation_sequence").get(pk=job_id)
    _start(job)
    try:
        sequence = job.item.animation_sequence
        output = assemble_gif(sequence, actor=job.created_by)
        _succeed(
            job,
            {
                "frame_count": sequence.frames.count(),
                "sequence_id": str(sequence.pk),
                "asset_id": str(output.pk),
            },
            "pillow-sequence-v1",
        )
    except Exception as exc:
        _fail(job, exc)
        raise


def _start(job):
    job.status = GenerationJob.Status.RUNNING
    job.started_at = timezone.now()
    job.attempts += 1
    job.error_code = ""
    job.error_message = ""
    job.save(
        update_fields=[
            "status",
            "started_at",
            "attempts",
            "error_code",
            "error_message",
            "updated_at",
        ]
    )


def _succeed(job, payload, model):
    job.status = GenerationJob.Status.SUCCEEDED
    job.output_payload = payload
    job.model = model
    job.completed_at = timezone.now()
    job.save(
        update_fields=["status", "output_payload", "model", "completed_at", "updated_at"]
    )


def _block(job, message):
    job.status = GenerationJob.Status.BLOCKED
    job.error_code = "provider_configuration"
    job.error_message = message
    job.completed_at = timezone.now()
    job.save(
        update_fields=[
            "status",
            "error_code",
            "error_message",
            "completed_at",
            "updated_at",
        ]
    )


def _fail(job, exc):
    job.status = GenerationJob.Status.FAILED
    job.error_code = exc.__class__.__name__
    job.error_message = str(exc)
    job.completed_at = timezone.now()
    job.output_payload = {
        "safe_error": str(exc),
        "task": job.job_type,
    }
    job.save(
        update_fields=[
            "status",
            "error_code",
            "error_message",
            "completed_at",
            "output_payload",
            "updated_at",
        ]
    )


@shared_task
def expire_trend_projects():
    from apps.core.models import CreativeProject

    expired = CreativeProject.objects.filter(
        status=CreativeProject.Status.ACTIVE,
        trend_topic__expires_at__lte=timezone.now(),
    )
    return expired.update(status=CreativeProject.Status.PAUSED)
