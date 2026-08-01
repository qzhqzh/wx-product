import io
import json
import zipfile

import pytest
from django.test import override_settings

from apps.assets.models import PlatformRuleSet
from apps.emoji.models import EmojiPack, GenerationJob
from apps.emoji.services import build_export_bundle, validate_pack
from apps.emoji.tasks import (
    enqueue_assemble_job,
    enqueue_frames_job,
    enqueue_image_job,
    enqueue_plan_job,
)


@pytest.mark.django_db(transaction=True)
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_static_pack_runs_from_brief_to_reproducible_export(static_pack, admin_user):
    plan_job = enqueue_plan_job(static_pack, provider="local", actor=admin_user)
    plan_job.refresh_from_db()
    static_pack.refresh_from_db()

    assert plan_job.status == GenerationJob.Status.SUCCEEDED
    assert static_pack.items.count() == 8
    assert static_pack.status == EmojiPack.Status.GENERATING

    for item in static_pack.items.all():
        job = enqueue_image_job(item, provider="local", actor=admin_user)
        job.refresh_from_db()
        assert job.status == GenerationJob.Status.SUCCEEDED

    static_pack.refresh_from_db()
    assert static_pack.status == EmojiPack.Status.CREATIVE_REVIEW
    assert static_pack.items.exclude(selected_asset=None).count() == 8
    assert all(
        [item.selected_asset.width, item.selected_asset.height] == [240, 240]
        for item in static_pack.items.select_related("selected_asset")
    )

    static_pack.items.update(is_approved=True)
    static_pack.status = EmojiPack.Status.PROCESSING
    static_pack.save(update_fields=["status", "updated_at"])
    validation = validate_pack(static_pack, actor=admin_user)
    assert validation.passed is True
    assert validation.error_count == 0
    assert validation.warning_count == 1

    bundle = build_export_bundle(static_pack, actor=admin_user)
    assert bundle.ruleset.version == "2026-07-seed"
    assert bundle.file.size_bytes > 0
    static_pack.refresh_from_db()
    assert static_pack.status == EmojiPack.Status.EXPORT_READY

    with bundle.file.file.open("rb") as source:
        with zipfile.ZipFile(io.BytesIO(source.read())) as archive:
            names = set(archive.namelist())
            assert "manifest.json" in names
            assert "support/cover.png" in names
            assert "support/icon.png" in names
            assert "support/banner.png" in names
            assert len([name for name in names if name.startswith("emoji/")]) == 8
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["ruleset"]["version"] == "2026-07-seed"
            assert len(manifest["items"]) == 8


@pytest.mark.django_db(transaction=True)
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_dynamic_sequence_creates_valid_gif(dynamic_single, admin_user):
    enqueue_plan_job(dynamic_single, provider="local", actor=admin_user)
    item = dynamic_single.items.get()
    enqueue_image_job(item, provider="local", actor=admin_user)
    item.refresh_from_db()

    job = enqueue_frames_job(item, frame_count=6, actor=admin_user)
    job.refresh_from_db()
    item.refresh_from_db()

    assert job.status == GenerationJob.Status.SUCCEEDED
    assert item.animation_sequence.frames.count() == 6
    assert item.selected_asset.original_name.endswith(".gif")
    assert item.selected_asset.frame_count == 6
    assert [item.selected_asset.width, item.selected_asset.height] == [240, 240]
    assert item.selected_asset.size_bytes <= 500 * 1024

    item.is_approved = True
    item.save(update_fields=["is_approved", "updated_at"])
    dynamic_single.status = EmojiPack.Status.PROCESSING
    dynamic_single.save(update_fields=["status", "updated_at"])
    run = validate_pack(dynamic_single, actor=admin_user)
    assert run.passed is True
    bundle = build_export_bundle(dynamic_single, actor=admin_user)
    assert bundle.manifest["items"][0]["filename"] == "emoji/01.gif"


@pytest.mark.django_db(transaction=True)
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_dynamic_timeline_reassembles_without_replacing_frames(dynamic_single, admin_user):
    enqueue_plan_job(dynamic_single, provider="local", actor=admin_user)
    item = dynamic_single.items.get()
    enqueue_image_job(item, provider="local", actor=admin_user)
    enqueue_frames_job(item, frame_count=4, actor=admin_user)
    sequence = item.animation_sequence
    original_frame_ids = list(sequence.frames.values_list("pk", flat=True))
    frames = list(sequence.frames.order_by("order"))
    frames[0].duration_ms = 360
    frames[0].save(update_fields=["duration_ms", "updated_at"])

    job = enqueue_assemble_job(sequence, actor=admin_user)
    job.refresh_from_db()
    sequence.refresh_from_db()

    assert job.status == GenerationJob.Status.SUCCEEDED
    assert list(sequence.frames.values_list("pk", flat=True)) == original_frame_ids
    assert sequence.output_asset.duration_ms >= 360


@pytest.mark.django_db(transaction=True)
@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    DEFAULT_AI_PROVIDER="openai",
    OPENAI_API_KEY="",
)
def test_missing_openai_key_blocks_only_the_job(static_pack, admin_user):
    job = enqueue_plan_job(static_pack, provider="openai", actor=admin_user)
    job.refresh_from_db()
    static_pack.refresh_from_db()

    assert job.status == GenerationJob.Status.BLOCKED
    assert job.error_code == "provider_configuration"
    assert "OPENAI_API_KEY" in job.error_message
    assert static_pack.status == EmojiPack.Status.DRAFT


@pytest.mark.django_db(transaction=True)
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_export_pins_ruleset_snapshot(static_pack, admin_user):
    enqueue_plan_job(static_pack, provider="local", actor=admin_user)
    for item in static_pack.items.all():
        enqueue_image_job(item, provider="local", actor=admin_user)
    static_pack.items.update(is_approved=True)
    static_pack.status = EmojiPack.Status.PROCESSING
    static_pack.save(update_fields=["status", "updated_at"])
    first_export = build_export_bundle(static_pack, actor=admin_user)

    old_ruleset = first_export.ruleset
    old_ruleset.is_active = False
    old_ruleset.save(update_fields=["is_active", "updated_at"])
    new_ruleset = PlatformRuleSet.objects.create(
        platform="wechat",
        product_type="emoji",
        media_type="static",
        version="2026-08-confirmed",
        effective_at=old_ruleset.effective_at,
        is_active=True,
        constraints={
            **old_ruleset.constraints,
            "item": {**old_ruleset.constraints["item"], "max_bytes": 480000},
        },
    )
    static_pack.ruleset = None
    static_pack.save(update_fields=["ruleset", "updated_at"])
    second_export = build_export_bundle(static_pack, actor=admin_user)

    assert first_export.ruleset == old_ruleset
    assert first_export.manifest["ruleset"]["version"] == "2026-07-seed"
    assert second_export.ruleset == new_ruleset
    assert second_export.manifest["ruleset"]["version"] == "2026-08-confirmed"
