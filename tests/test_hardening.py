import io

import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from PIL import Image
from rest_framework.test import APIClient

from apps.assets.models import AssetVersion, PlatformRuleSet
from apps.assets.services import create_asset
from apps.core.export_integrity import export_is_current
from apps.core.media_hardening import AssetValidationError
from apps.core.models import TransitionEvent
from apps.emoji.models import EmojiItem, EmojiPack, ExportBundle
from apps.emoji.pipeline import transition_pack
from apps.emoji.tasks import enqueue_plan_job, plan_pack_task
from apps.redpacket.models import RedPacketCampaign, RedPacketOrder


@pytest.mark.django_db
def test_template_write_requires_pipeline_role():
    user = get_user_model().objects.create_user(username="viewer", password="password")
    client = APIClient()
    client.force_login(user)

    response = client.post(reverse("project-create"), {})

    assert response.status_code == 403


@pytest.mark.django_db
def test_asset_view_ignores_spoofed_html_mime(admin_user):
    asset = create_asset(
        content=b"<script>document.body.textContent = document.cookie</script>",
        filename="payload.md",
        kind=AssetVersion.Kind.DOCUMENT,
        source=AssetVersion.Source.UPLOAD,
        actor=admin_user,
        mime_type="text/html",
    )
    client = APIClient()
    client.force_login(admin_user)

    response = client.get(reverse("view-asset", kwargs={"asset_id": asset.pk}))

    assert response.status_code == 200
    assert response["Content-Type"].startswith("text/markdown")
    assert response["Content-Disposition"].startswith("attachment;")
    assert response["Content-Security-Policy"] == "default-src 'none'; sandbox"


@pytest.mark.django_db
@override_settings(ASSET_MAX_IMAGE_PIXELS=100)
def test_image_pixel_budget_rejects_decompression_bomb(admin_user):
    output = io.BytesIO()
    Image.new("RGB", (11, 11), "white").save(output, format="PNG")

    with pytest.raises(AssetValidationError, match="像素数"):
        create_asset(
            content=output.getvalue(),
            filename="oversized.png",
            kind=AssetVersion.Kind.SOURCE,
            source=AssetVersion.Source.UPLOAD,
            actor=admin_user,
            mime_type="image/png",
        )


@pytest.mark.django_db
def test_strict_json_parser_preserves_false(static_pack, admin_user):
    item = EmojiItem.objects.create(
        pack=static_pack,
        order=1,
        meaning="收到",
        is_approved=True,
    )
    client = APIClient()
    client.force_login(admin_user)

    response = client.post(
        reverse(
            "api-approve-item",
            kwargs={"pack_id": static_pack.pk, "item_id": item.pk},
        ),
        {"approved": "false"},
        format="json",
    )

    assert response.status_code == 200
    item.refresh_from_db()
    assert item.is_approved is False


@pytest.mark.django_db
def test_invalid_integer_returns_400(static_pack, admin_user):
    item = EmojiItem.objects.create(pack=static_pack, order=1, meaning="收到")
    client = APIClient()
    client.force_login(admin_user)

    response = client.post(
        reverse(
            "api-generate-frames",
            kwargs={"pack_id": static_pack.pk, "item_id": item.pk},
        ),
        {"frame_count": "abc"},
        format="json",
    )

    assert response.status_code == 400
    assert "frame_count" in response.json()


@pytest.mark.django_db(transaction=True)
def test_same_celery_job_is_only_executed_once(static_pack, admin_user):
    transition_pack(
        static_pack,
        EmojiPack.Status.BRIEF_APPROVED,
        actor=admin_user,
        note="test",
    )
    job = enqueue_plan_job(
        static_pack,
        provider="local",
        actor=admin_user,
        dispatch=False,
    )

    plan_pack_task.run(str(job.pk))
    plan_pack_task.run(str(job.pk))

    job.refresh_from_db()
    assert job.status == job.Status.SUCCEEDED
    assert job.attempts == 1
    assert static_pack.items.count() == static_pack.target_count


@pytest.mark.django_db
def test_export_fingerprint_detects_upstream_change(static_pack, admin_user):
    ruleset = PlatformRuleSet.objects.filter(
        product_type="emoji", media_type="static", is_active=True
    ).first()
    asset = create_asset(
        content=b"PK\x05\x06" + b"\x00" * 18,
        filename="export.zip",
        kind=AssetVersion.Kind.EXPORT,
        source=AssetVersion.Source.EXPORTER,
        actor=admin_user,
        mime_type="application/zip",
    )
    bundle = ExportBundle.objects.create(
        pack=static_pack,
        ruleset=ruleset,
        file=asset,
        manifest={},
        checksum_sha256=asset.checksum_sha256,
        created_by=admin_user,
    )
    bundle.refresh_from_db()
    assert export_is_current(bundle)

    static_pack.creative_brief = "导出后修改的 Brief"
    static_pack.save(update_fields=["creative_brief", "updated_at"])

    bundle.refresh_from_db()
    assert not export_is_current(bundle)


@pytest.mark.django_db
def test_distribution_rejects_non_available_order(red_packet_campaign, admin_user):
    red_packet_campaign.status = RedPacketCampaign.Status.DISTRIBUTING
    red_packet_campaign.save(update_fields=["status", "updated_at"])
    order = RedPacketOrder.objects.create(
        campaign=red_packet_campaign,
        quantity=10,
        status=RedPacketOrder.Status.PLANNED,
        purchased_at=timezone.now(),
        created_by=admin_user,
    )
    client = APIClient()
    client.force_login(admin_user)

    response = client.post(
        reverse(
            "api-red-packet-distribution",
            kwargs={
                "campaign_id": red_packet_campaign.pk,
                "order_id": order.pk,
            },
        ),
        {"quantity": 1},
        format="json",
    )

    assert response.status_code == 409
    assert order.distributions.count() == 0


@pytest.mark.django_db
def test_direct_status_write_gets_fallback_audit(
    static_pack, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        static_pack.status = EmojiPack.Status.GENERATING
        static_pack.save(update_fields=["status", "updated_at"])

    assert TransitionEvent.objects.filter(
        object_type="emoji_pack",
        object_id=static_pack.pk,
        from_state=EmojiPack.Status.DRAFT,
        to_state=EmojiPack.Status.GENERATING,
        action="implicit_transition",
    ).exists()
