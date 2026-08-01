import os
from datetime import datetime

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.assets.models import PlatformRuleSet
from apps.emoji.models import PromptPreset, PromptTemplateVersion

from ...models import ProductLine


class Command(BaseCommand):
    help = "Create product lines, roles, rule sets, prompts, and optional first admin."

    def handle(self, *args, **options):
        lines = [
            {
                "code": "emoji",
                "name": "表情包",
                "description": "静态与序列帧动态表情的完整生产、QA 和投稿闭环。",
                "status": ProductLine.Status.ACTIVE,
                "sort_order": 10,
                "adapter_path": "apps.emoji.adapters.EmojiProductLineAdapter",
            },
            {
                "code": "red-packet-cover",
                "name": "红包封面",
                "description": "封面故事、权利材料、审核、下单和发放库存。",
                "status": ProductLine.Status.ACTIVE,
                "sort_order": 20,
                "adapter_path": (
                    "apps.redpacket.adapters.RedPacketProductLineAdapter"
                ),
            },
            {
                "code": "mini-program",
                "name": "小程序",
                "description": "PRD、构建、隐私合规、体验版、审核和发布。",
                "status": ProductLine.Status.ACTIVE,
                "sort_order": 30,
                "adapter_path": (
                    "apps.miniprogram.adapters.MiniProgramProductLineAdapter"
                ),
            },
        ]
        for line in lines:
            ProductLine.objects.update_or_create(
                code=line["code"],
                defaults={
                    key: value for key, value in line.items() if key != "code"
                },
            )

        role_permissions = {
            "planner": {"view", "add", "change"},
            "creator": {"view", "add", "change"},
            "reviewer": {"view", "change"},
            "operator": {"view", "add", "change"},
            "admin": {"view", "add", "change", "delete"},
        }
        app_labels = {"core", "assets", "emoji", "redpacket", "miniprogram"}
        permissions = Permission.objects.filter(content_type__app_label__in=app_labels)
        for role, actions in role_permissions.items():
            group, _ = Group.objects.get_or_create(name=role)
            group.permissions.set(
                permission
                for permission in permissions
                if permission.codename.split("_", 1)[0] in actions
            )

        source_url = "https://sticker.weixin.qq.com/"
        shared_support = {
            "cover": [240, 240],
            "icon": [50, 50],
            "banner": [750, 400],
        }
        rules = [
            (
                "static",
                {
                    "allowed_counts": [8, 16, 24],
                    "item": {
                        "format": "PNG",
                        "size": [240, 240],
                        "max_bytes": 512000,
                    },
                    "support": shared_support,
                },
            ),
            (
                "dynamic",
                {
                    "allowed_counts": [8, 16, 24],
                    "item": {
                        "format": "GIF",
                        "size": [240, 240],
                        "max_bytes": 512000,
                        "min_frames": 2,
                    },
                    "support": shared_support,
                },
            ),
        ]
        for media_type, constraints in rules:
            PlatformRuleSet.objects.update_or_create(
                platform="wechat",
                product_type="emoji",
                media_type=media_type,
                version="2026-07-seed",
                defaults={
                    "effective_at": datetime(
                        2026, 7, 29, tzinfo=timezone.get_current_timezone()
                    ),
                    "is_active": True,
                    "source_url": source_url,
                    "constraints": constraints,
                    "notes": (
                        "初始规则种子；每次投稿前必须在微信表情开放平台复核，"
                        "确认后创建新版本，不直接覆盖历史规则。"
                    ),
                },
            )

        seed_effective_at = datetime(
            2026, 7, 29, tzinfo=timezone.get_current_timezone()
        )
        PlatformRuleSet.objects.update_or_create(
            platform="wechat",
            product_type="red_packet_cover",
            media_type="static",
            version="2026-07-seed",
            defaults={
                "effective_at": seed_effective_at,
                "is_active": True,
                "constraints": {
                    "cover": {
                        "formats": ["PNG", "JPG", "JPEG"],
                        "size": [957, 1278],
                        "max_bytes": 2 * 1024 * 1024,
                    },
                    "preview": {"format": "PNG", "size": [750, 400]},
                    "story_required": True,
                    "rights_required": False,
                },
                "notes": (
                    "红包封面可运行规则种子；尺寸、体积、权利材料和下单要求"
                    "必须在正式提交前按微信平台当期规则创建新版本。"
                ),
            },
        )
        PlatformRuleSet.objects.update_or_create(
            platform="wechat",
            product_type="mini_program",
            media_type="release",
            version="2026-07-seed",
            defaults={
                "effective_at": seed_effective_at,
                "is_active": True,
                "constraints": {
                    "build": {
                        "formats": ["ZIP"],
                        "max_bytes": 20 * 1024 * 1024,
                    },
                    "required_artifacts": [
                        "build_package",
                        "experience_qr",
                        "screenshot",
                    ],
                    "min_screenshots": 2,
                    "privacy_summary_required": True,
                },
                "notes": (
                    "小程序发布可运行规则种子；正式提审前需按当前类目、隐私"
                    "保护指引和微信公众平台要求创建确认版本。"
                ),
            },
        )

        PromptTemplateVersion.objects.update_or_create(
            code="emoji-semantic-plan",
            version=1,
            defaults={
                "purpose": "生成高频聊天语义矩阵",
                "template": (
                    "根据专辑名称、语气、Brief 和目标数量生成互不重复的聊天语义项，"
                    "每项包含 meaning、copy_text、action、prompt。"
                ),
                "is_active": True,
            },
        )
        prompt_presets = [
            (
                PromptPreset.Category.BASE,
                "微信表情基础约束",
                "围绕{character}角色表现“{meaning}”，动作是{action}，语气保持{tone}。",
                "把角色、语义和动作合成稳定的基础描述。",
            ),
            (
                PromptPreset.Category.STYLE,
                "清爽贴纸风",
                "微信表情贴纸风格，圆润简洁，色块清楚，轮廓干净。",
                "适合聊天场景的常用视觉风格。",
            ),
            (
                PromptPreset.Category.COMPOSITION,
                "小尺寸安全构图",
                "单一角色主体居中，四周保留安全边距，表情和动作在小尺寸下仍清晰。",
                "避免主体贴边或细节在缩放后丢失。",
            ),
            (
                PromptPreset.Category.QUALITY,
                "透明背景成品要求",
                "透明背景，高对比度，无边框，可直接规范化为微信表情 PNG。",
                "补充输出格式和可用性要求。",
            ),
            (
                PromptPreset.Category.NEGATIVE,
                "平台安全负向词",
                "水印、二维码、真实品牌标识、第三方 IP、复杂背景、密集小字、低清晰度",
                "生成时统一排除常见平台风险。",
            ),
        ]
        for category, name, content, description in prompt_presets:
            preset, created = PromptPreset.objects.update_or_create(
                category=category,
                name=name,
                defaults={
                    "content": content,
                    "description": description,
                    "is_active": True,
                },
            )
            if created and not PromptPreset.objects.filter(
                category=category,
                is_default=True,
            ).exclude(pk=preset.pk).exists():
                preset.is_default = True
                preset.save(update_fields=["is_default", "updated_at"])

        password = os.getenv("DJANGO_SUPERUSER_PASSWORD", "")
        username = os.getenv("DJANGO_SUPERUSER_USERNAME", "admin")
        if password:
            user_model = get_user_model()
            user, created = user_model.objects.get_or_create(
                username=username,
                defaults={"email": os.getenv("DJANGO_SUPERUSER_EMAIL", "")},
            )
            if created or not user.is_superuser:
                user.is_staff = True
                user.is_superuser = True
                user.set_password(password)
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Superuser ready: {username}"))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "DJANGO_SUPERUSER_PASSWORD is empty; skipped superuser creation."
                )
            )
        self.stdout.write(self.style.SUCCESS("Pipeline bootstrap complete."))
