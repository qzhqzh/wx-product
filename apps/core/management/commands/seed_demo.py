from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.emoji.models import EmojiPack
from apps.emoji.prompts import attach_default_presets
from apps.emoji.tasks import (
    enqueue_image_job,
    enqueue_plan_job,
    generate_item_task,
    plan_pack_task,
)
from apps.miniprogram.models import MiniProgramRelease
from apps.miniprogram.services import generate_demo_release
from apps.redpacket.models import RedPacketCampaign
from apps.redpacket.services import generate_demo_designs

from ...models import CreativeProject, IPCharacter, IPCharacterVersion, ProductLine


class Command(BaseCommand):
    help = "Create an idempotent original-IP demo project and optional local generation jobs."

    def add_arguments(self, parser):
        parser.add_argument(
            "--produce",
            action="store_true",
            help="Queue local semantic planning and image generation for the static demo pack.",
        )

    def handle(self, *args, **options):
        product_line = ProductLine.objects.get(code="emoji")
        owner = (
            get_user_model()
            .objects.filter(is_superuser=True)
            .order_by("date_joined")
            .first()
        )
        character, _ = IPCharacter.objects.update_or_create(
            code="tuantuan",
            defaults={
                "name": "团团",
                "summary": "一只在都市生活里认真摸鱼、偶尔热血的原创圆脸小熊。",
                "created_by": owner,
            },
        )
        character_version, _ = IPCharacterVersion.objects.update_or_create(
            character=character,
            version=1,
            defaults={
                "personality": "温和、机灵、有一点嘴硬，适合工作与好友聊天。",
                "style_anchors": ["圆脸小熊", "粗线条", "大表情", "透明背景"],
                "forbidden_elements": ["真实品牌标识", "第三方角色特征", "复杂小字"],
                "palette": ["#E55353", "#F4C66A", "#2F3944", "#FFFFFF"],
                "reference_notes": "演示角色；正式生产前应补齐角色三视图与权利材料。",
                "is_locked": True,
                "created_by": owner,
            },
        )
        project, _ = CreativeProject.objects.update_or_create(
            title="团团原创 IP 首发表情",
            product_line=product_line,
            defaults={
                "lane": CreativeProject.Lane.IP,
                "status": CreativeProject.Status.ACTIVE,
                "description": "覆盖常用聊天语义，验证静态与动态表情生产、QA、导出和投稿登记。",
                "owner": owner,
                "character_version": character_version,
            },
        )
        static_pack, _ = EmojiPack.objects.update_or_create(
            project=project,
            name="团团上班日常",
            defaults={
                "pack_type": EmojiPack.PackType.ALBUM,
                "media_type": EmojiPack.MediaType.STATIC,
                "target_count": 8,
                "audience": "职场新人、朋友群和日常社交用户",
                "tone": "轻松、有梗、克制，不使用网络攻击性表达",
                "creative_brief": (
                    "围绕收到、谢谢、加油、无语、下班、开会、在吗、晚安八个高频语义，"
                    "角色一致，轮廓清晰，手机小尺寸下仍然易读。"
                ),
                "negative_prompt": "第三方 IP、品牌 Logo、密集小字、写实照片、低对比度",
                "owner": owner,
            },
        )
        attach_default_presets(static_pack)
        dynamic_pack, _ = EmojiPack.objects.update_or_create(
            project=project,
            name="团团动起来",
            defaults={
                "pack_type": EmojiPack.PackType.ALBUM,
                "media_type": EmojiPack.MediaType.DYNAMIC,
                "target_count": 8,
                "audience": "熟人聊天与社群互动",
                "tone": "动作夸张但循环平顺",
                "creative_brief": "从静态母帧生成 6 帧轻量循环动效，优先点头、挥手和弹跳。",
                "negative_prompt": "快速闪烁、复杂背景、第三方 IP、品牌 Logo",
                "owner": owner,
            },
        )
        attach_default_presets(dynamic_pack)
        red_packet_line = ProductLine.objects.get(code="red-packet-cover")
        red_packet_project, _ = CreativeProject.objects.update_or_create(
            title="团团新年红包封面",
            product_line=red_packet_line,
            defaults={
                "lane": CreativeProject.Lane.IP,
                "status": CreativeProject.Status.ACTIVE,
                "description": "验证红包封面设计、权利审核、QA、提审、下单和发放闭环。",
                "owner": owner,
                "character_version": character_version,
            },
        )
        red_packet_campaign, _ = RedPacketCampaign.objects.update_or_create(
            project=red_packet_project,
            name="团团把好运装满",
            defaults={
                "audience": "好友、社群成员与品牌活动参与者",
                "cover_story": (
                    "团团把一整年的小确幸装进红包，分享给每个认真生活的人。"
                ),
                "greeting": "好运装满，心愿达成",
                "style_keywords": ["团团", "红金", "圆润", "节庆但克制"],
                "design_target": 3,
                "planned_quantity": 300,
                "owner": owner,
            },
        )
        mini_program_line = ProductLine.objects.get(code="mini-program")
        mini_program_project, _ = CreativeProject.objects.update_or_create(
            title="团团灵感簿小程序",
            product_line=mini_program_line,
            defaults={
                "lane": CreativeProject.Lane.PRODUCT,
                "status": CreativeProject.Status.ACTIVE,
                "description": "验证小程序 PRD、构建、体验版、隐私合规、测试和发布闭环。",
                "owner": owner,
            },
        )
        mini_program_release, _ = MiniProgramRelease.objects.update_or_create(
            project=mini_program_project,
            version="1.0.0",
            defaults={
                "name": "团团灵感簿",
                "release_type": MiniProgramRelease.ReleaseType.INITIAL,
                "service_category": "工具 / 效率",
                "prd_summary": (
                    "用户可以记录灵感、按主题归档并导出；首版不包含社交和支付。"
                ),
                "change_log": "首次发布：灵感记录、主题归档、离线草稿与导出。",
                "privacy_summary": (
                    "仅在用户主动导出时访问文件能力；不收集通讯录、位置或设备标识。"
                ),
                "owner": owner,
            },
        )

        if options["produce"]:
            plan_job = enqueue_plan_job(
                static_pack,
                provider="local",
                actor=owner,
                dispatch=False,
            )
            if plan_job.status != plan_job.Status.SUCCEEDED:
                plan_pack_task.run(str(plan_job.pk))
            for item in static_pack.items.all():
                image_job = enqueue_image_job(
                    item,
                    provider="local",
                    actor=owner,
                    dispatch=False,
                )
                if image_job.status != image_job.Status.SUCCEEDED:
                    generate_item_task.run(str(image_job.pk))
            if not red_packet_campaign.designs.exists():
                generate_demo_designs(red_packet_campaign, actor=owner)
            if not mini_program_release.artifacts.exists():
                generate_demo_release(mini_program_release, actor=owner)
            self.stdout.write("Local demo assets produced.")

        self.stdout.write(
            self.style.SUCCESS(
                f"Demo project ready: {project.title} ({project.pk})"
            )
        )
