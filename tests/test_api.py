import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.emoji.models import EmojiPack
from apps.emoji.tasks import enqueue_frames_job, enqueue_image_job, enqueue_plan_job


@pytest.mark.django_db
def test_dashboard_and_workbench_require_login(static_pack):
    client = APIClient()
    response = client.get(reverse("dashboard"))
    assert response.status_code == 302
    assert "/login/" in response.url

    response = client.get(reverse("pack-workbench", kwargs={"pack_id": static_pack.pk}))
    assert response.status_code == 302


@pytest.mark.django_db
def test_authenticated_user_can_load_private_pack_json(static_pack, creator_user):
    client = APIClient()
    client.force_login(creator_user)

    response = client.get(reverse("api-pack", kwargs={"pack_id": static_pack.pk}))

    assert response.status_code == 200
    assert response.json()["name"] == static_pack.name
    assert response.json()["items"] == []


@pytest.mark.django_db
def test_role_permission_blocks_unassigned_user(static_pack, django_user_model):
    user = django_user_model.objects.create_user(username="viewer", password="test-password")
    client = APIClient()
    client.force_login(user)

    response = client.post(
        reverse("api-plan-pack", kwargs={"pack_id": static_pack.pk}),
        {"provider": "local"},
        format="json",
    )

    assert response.status_code == 403


@pytest.mark.django_db
def test_product_line_routes_are_registered(admin_user):
    client = APIClient()
    client.force_login(admin_user)

    expected = {
        "red-packet-cover": "红包封面流水线",
        "mini-program": "小程序发布流水线",
    }
    for code, text in expected.items():
        response = client.get(reverse("product-placeholder", kwargs={"code": code}))
        assert response.status_code == 200
        assert text in response.content.decode()


@pytest.mark.django_db
def test_invalid_transition_returns_conflict(static_pack, admin_user):
    client = APIClient()
    client.force_login(admin_user)

    response = client.post(
        reverse("api-transition-pack", kwargs={"pack_id": static_pack.pk}),
        {"to_state": EmojiPack.Status.PUBLISHED},
        format="json",
    )

    assert response.status_code == 409


@pytest.mark.django_db(transaction=True)
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_sequence_api_can_swap_frames_without_regenerating_them(
    dynamic_single, admin_user
):
    enqueue_plan_job(dynamic_single, provider="local", actor=admin_user)
    item = dynamic_single.items.get()
    enqueue_image_job(item, provider="local", actor=admin_user)
    enqueue_frames_job(item, frame_count=3, actor=admin_user)
    frames = list(item.animation_sequence.frames.order_by("order"))
    original_ids = {frame.pk for frame in frames}
    client = APIClient()
    client.force_login(admin_user)

    response = client.patch(
        reverse(
            "api-sequence",
            kwargs={"pack_id": dynamic_single.pk, "item_id": item.pk},
        ),
        {
            "frames": [
                {"id": frames[1].pk, "duration_ms": 240},
                {"id": frames[0].pk, "duration_ms": 100},
                {"id": frames[2].pk, "duration_ms": 120},
            ]
        },
        format="json",
    )

    assert response.status_code == 202
    reordered = list(item.animation_sequence.frames.order_by("order"))
    assert {frame.pk for frame in reordered} == original_ids
    assert [frame.pk for frame in reordered[:2]] == [frames[1].pk, frames[0].pk]
    assert reordered[0].duration_ms == 240
