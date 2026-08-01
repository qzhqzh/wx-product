import json
from types import SimpleNamespace

import pytest
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APIClient

from apps.emoji.models import EmojiPack, GenerationJob, PromptPreset
from apps.emoji.prompts import attach_default_presets
from apps.emoji.tasks import enqueue_image_job, enqueue_plan_job
from apps.integrations.providers import ProviderCapabilityError, QwenProvider, get_provider


@pytest.mark.django_db
def test_emoji_has_standalone_menu_and_prompt_library(admin_user):
    client = APIClient()
    client.force_login(admin_user)

    pack_response = client.get(reverse("emoji-pack-list"))
    prompt_response = client.get(reverse("emoji-prompt-library"))

    assert pack_response.status_code == 200
    assert "表情包流水线" in pack_response.content.decode()
    assert "项目与选题" in pack_response.content.decode()
    assert prompt_response.status_code == 200
    assert "表情包提示词库" in prompt_response.content.decode()
    assert PromptPreset.objects.filter(is_default=True).count() == 5


@pytest.mark.django_db
def test_standalone_pack_creation_applies_default_prompts(project, admin_user):
    client = APIClient()
    client.force_login(admin_user)

    response = client.post(
        reverse("emoji-pack-create"),
        {
            "project": str(project.pk),
            "name": "小红常用回复",
            "pack_type": "album",
            "media_type": "static",
            "target_count": 8,
            "audience": "好友与同事",
            "tone": "简洁友好",
            "creative_brief": "覆盖工作和好友聊天。",
            "negative_prompt": "模糊、低对比度",
        },
    )

    assert response.status_code == 302
    pack = EmojiPack.objects.get(name="小红常用回复")
    assert pack.prompt_presets.count() == 5
    assert response.url == reverse("pack-workbench", kwargs={"pack_id": pack.pk})


@pytest.mark.django_db
def test_prompt_library_can_replace_default_and_disable_preset(admin_user):
    old_default = PromptPreset.objects.get(
        category=PromptPreset.Category.STYLE,
        is_default=True,
    )
    client = APIClient()
    client.force_login(admin_user)

    response = client.post(
        reverse("emoji-prompt-create"),
        {
            "name": "软陶立体风",
            "category": PromptPreset.Category.STYLE,
            "description": "常用三维软陶质感",
            "content": "柔和软陶质感，圆润体积，干净棚拍光。",
            "is_default": "on",
            "is_active": "on",
        },
    )

    assert response.status_code == 302
    preset = PromptPreset.objects.get(name="软陶立体风")
    old_default.refresh_from_db()
    assert preset.is_default is True
    assert old_default.is_default is False

    response = client.post(reverse("emoji-prompt-toggle", kwargs={"preset_id": preset.pk}))
    preset.refresh_from_db()
    assert response.status_code == 302
    assert preset.is_active is False
    assert preset.is_default is False


@pytest.mark.django_db(transaction=True)
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_generation_job_freezes_composed_prompt_snapshot(static_pack, admin_user):
    attach_default_presets(static_pack)
    enqueue_plan_job(static_pack, provider="local", actor=admin_user)
    item = static_pack.items.first()

    job = enqueue_image_job(item, provider="local", actor=admin_user, dispatch=False)

    assert "小红角色" in job.prompt
    assert "微信表情贴纸风格，圆润简洁" in job.prompt
    assert "平台安全负向词" not in job.prompt
    assert "水印" in job.input_payload["negative_prompt"]
    assert len(job.input_payload["prompt_preset_ids"]) == 5


@pytest.mark.django_db(transaction=True)
@override_settings(CELERY_TASK_ALWAYS_EAGER=True)
def test_item_prompt_can_be_edited_and_optimized(static_pack, admin_user):
    enqueue_plan_job(static_pack, provider="local", actor=admin_user)
    item = static_pack.items.first()
    client = APIClient()
    client.force_login(admin_user)
    endpoint = reverse(
        "api-item-prompt",
        kwargs={"pack_id": static_pack.pk, "item_id": item.pk},
    )

    response = client.patch(
        endpoint,
        {"prompt": "小红认真点头，透明背景"},
        format="json",
    )
    assert response.status_code == 200

    response = client.post(
        endpoint,
        {"provider": "local", "prompt": "小红认真点头，透明背景"},
        format="json",
    )
    assert response.status_code == 202
    job = GenerationJob.objects.get(pk=response.json()["id"])
    item.refresh_from_db()
    assert job.status == GenerationJob.Status.SUCCEEDED
    assert "聊天含义" in item.prompt


@pytest.mark.django_db(transaction=True)
@override_settings(CELERY_TASK_ALWAYS_EAGER=True, DASHSCOPE_API_KEY="")
def test_missing_qwen_key_blocks_only_prompt_job(static_pack, admin_user):
    enqueue_plan_job(static_pack, provider="local", actor=admin_user)
    item = static_pack.items.first()
    original_prompt = item.prompt
    client = APIClient()
    client.force_login(admin_user)

    response = client.post(
        reverse(
            "api-item-prompt",
            kwargs={"pack_id": static_pack.pk, "item_id": item.pk},
        ),
        {"provider": "qwen", "prompt": original_prompt},
        format="json",
    )

    assert response.status_code == 202
    job = GenerationJob.objects.get(pk=response.json()["id"])
    item.refresh_from_db()
    assert job.status == GenerationJob.Status.BLOCKED
    assert "DASHSCOPE_API_KEY" in job.error_message
    assert item.prompt == original_prompt


@override_settings(
    DASHSCOPE_API_KEY="test-key",
    QWEN_BASE_URL="https://example.invalid/compatible-mode/v1",
    QWEN_TEXT_MODEL="qwen3.7-plus",
)
def test_qwen_provider_uses_text_output_and_rejects_image_generation(monkeypatch):
    payload = {
        "summary": "覆盖高频聊天语义。",
        "items": [
            {
                "meaning": "收到",
                "copy_text": "收到！",
                "action": "认真点头",
                "prompt": "小红认真点头，透明背景",
            }
        ],
    }

    def create(**kwargs):
        content = (
            json.dumps(payload, ensure_ascii=False)
            if kwargs.get("response_format")
            else "小红认真点头，主体居中，透明背景"
        )
        message = SimpleNamespace(content=content)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])

    fake_client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    monkeypatch.setattr("openai.OpenAI", lambda **kwargs: fake_client)

    provider = QwenProvider()
    plan = provider.plan_pack(name="测试", brief="测试", tone="友好", count=1)
    optimized = provider.optimize_prompt(
        prompt="小红点头",
        meaning="收到",
        action="点头",
        tone="友好",
    )

    assert plan.items[0].meaning == "收到"
    assert optimized.endswith("透明背景")
    with pytest.raises(ProviderCapabilityError, match="不能生图"):
        get_provider("qwen", capability="image")
