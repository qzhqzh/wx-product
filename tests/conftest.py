import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from apps.core.models import (
    CreativeProject,
    IPCharacter,
    IPCharacterVersion,
    ProductLine,
)
from apps.emoji.models import EmojiPack
from apps.miniprogram.models import MiniProgramRelease
from apps.redpacket.models import RedPacketCampaign


@pytest.fixture(autouse=True)
def bootstrap(db):
    call_command("bootstrap_pipeline", verbosity=0)


@pytest.fixture
def admin_user(db):
    return get_user_model().objects.create_superuser(
        username="admin", email="admin@example.com", password="test-password"
    )


@pytest.fixture
def creator_user(db):
    user = get_user_model().objects.create_user(
        username="creator", password="test-password"
    )
    user.groups.add(user.groups.model.objects.get(name="creator"))
    return user


@pytest.fixture
def project(admin_user):
    character = IPCharacter.objects.create(
        code="xiaohong",
        name="小红",
        summary="内部原创圆脸角色",
        created_by=admin_user,
    )
    version = IPCharacterVersion.objects.create(
        character=character,
        version=1,
        personality="热情但不吵闹",
        style_anchors=["圆脸", "红色主体", "透明背景"],
        forbidden_elements=["第三方 logo", "二维码"],
        is_locked=True,
        created_by=admin_user,
    )
    return CreativeProject.objects.create(
        title="小红日常第一季",
        product_line=ProductLine.objects.get(code="emoji"),
        lane=CreativeProject.Lane.IP,
        owner=admin_user,
        character_version=version,
        due_at=timezone.now() + timezone.timedelta(days=7),
    )


@pytest.fixture
def static_pack(project, admin_user):
    return EmojiPack.objects.create(
        project=project,
        name="小红上班记",
        pack_type=EmojiPack.PackType.ALBUM,
        media_type=EmojiPack.MediaType.STATIC,
        target_count=8,
        tone="清爽、直接",
        creative_brief="覆盖工作群里的高频回复。",
        owner=admin_user,
    )


@pytest.fixture
def dynamic_single(project, admin_user):
    return EmojiPack.objects.create(
        project=project,
        name="小红点头",
        pack_type=EmojiPack.PackType.SINGLE,
        media_type=EmojiPack.MediaType.DYNAMIC,
        target_count=1,
        tone="轻快",
        creative_brief="做一个明确的收到动作。",
        owner=admin_user,
    )


@pytest.fixture
def red_packet_campaign(admin_user):
    project = CreativeProject.objects.create(
        title="小红新年红包封面",
        product_line=ProductLine.objects.get(code="red-packet-cover"),
        lane=CreativeProject.Lane.PRODUCT,
        owner=admin_user,
    )
    return RedPacketCampaign.objects.create(
        project=project,
        name="小红好运封面",
        audience="好友与社群用户",
        cover_story="小红收集日常好运，并把祝福分享给朋友。",
        greeting="好运常在",
        style_keywords=["红色", "圆润", "原创角色"],
        design_target=3,
        planned_quantity=100,
        owner=admin_user,
    )


@pytest.fixture
def mini_program_release(admin_user):
    project = CreativeProject.objects.create(
        title="小红任务簿小程序",
        product_line=ProductLine.objects.get(code="mini-program"),
        lane=CreativeProject.Lane.PRODUCT,
        owner=admin_user,
    )
    return MiniProgramRelease.objects.create(
        project=project,
        name="小红任务簿",
        app_id="wx-test-app-id",
        version="1.0.0",
        release_type=MiniProgramRelease.ReleaseType.INITIAL,
        service_category="工具 / 效率",
        prd_summary="用户创建任务、标记完成并导出；首版不包含支付和社交。",
        change_log="首次发布任务清单与导出。",
        privacy_summary="仅在用户主动导出时访问文件能力，不采集位置或通讯录。",
        owner=admin_user,
    )
