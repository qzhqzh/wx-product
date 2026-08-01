import hashlib
import uuid
from pathlib import Path

from django.conf import settings
from django.core.validators import FileExtensionValidator
from django.db import models

from apps.core.models import CreativeProject, TimestampedModel


def asset_upload_path(instance, filename):
    suffix = Path(filename).suffix.lower()
    return f"assets/{instance.kind}/{uuid.uuid4()}{suffix}"


def proof_upload_path(instance, filename):
    return f"rights/{instance.project_id}/{uuid.uuid4()}{Path(filename).suffix.lower()}"


class AssetVersion(TimestampedModel):
    class Kind(models.TextChoices):
        SOURCE = "source", "源素材"
        REFERENCE = "reference", "角色参考图"
        CANDIDATE = "candidate", "生成候选"
        FINAL_STATIC = "final_static", "静态成品"
        ANIMATION_FRAME = "animation_frame", "序列帧"
        FINAL_GIF = "final_gif", "动态成品"
        COVER = "cover", "专辑封面"
        ICON = "icon", "聊天图标"
        BANNER = "banner", "详情横幅"
        RED_PACKET_COVER = "red_packet_cover", "红包封面成品"
        RED_PACKET_PREVIEW = "red_packet_preview", "红包封面预览"
        BUILD_PACKAGE = "build_package", "小程序构建包"
        EXPERIENCE_QR = "experience_qr", "小程序体验码"
        SCREENSHOT = "screenshot", "小程序截图"
        DOCUMENT = "document", "业务文档"
        EXPORT = "export", "导出包"

    class Source(models.TextChoices):
        UPLOAD = "upload", "人工上传"
        LOCAL = "local", "本地演示"
        OPENAI = "openai", "OpenAI"
        PROCESSOR = "processor", "媒体处理器"
        EXPORTER = "exporter", "导出器"

    file = models.FileField(upload_to=asset_upload_path)
    original_name = models.CharField(max_length=255, blank=True)
    kind = models.CharField(max_length=24, choices=Kind.choices)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.UPLOAD)
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="derivatives",
    )
    mime_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.PositiveBigIntegerField(default=0)
    width = models.PositiveIntegerField(default=0)
    height = models.PositiveIntegerField(default=0)
    frame_count = models.PositiveIntegerField(default=1)
    duration_ms = models.PositiveIntegerField(default=0)
    checksum_sha256 = models.CharField(max_length=64, db_index=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_asset_versions",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.original_name or self.file.name

    @staticmethod
    def checksum(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()


class RightsEvidence(TimestampedModel):
    class Kind(models.TextChoices):
        ORIGINAL = "original", "原创声明"
        AUTHORIZATION = "authorization", "版权授权"
        PORTRAIT = "portrait", "肖像授权"
        TRADEMARK = "trademark", "商标证明"
        OTHER = "other", "其他"

    project = models.ForeignKey(
        CreativeProject, on_delete=models.CASCADE, related_name="rights_evidence"
    )
    asset = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rights_evidence",
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    rights_owner = models.CharField(max_length=160)
    proof_file = models.FileField(
        upload_to=proof_upload_path,
        validators=[FileExtensionValidator(["pdf", "png", "jpg", "jpeg", "zip"])],
        blank=True,
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_rights_evidence",
    )

    class Meta:
        ordering = ["-created_at"]


class PlatformRuleSet(TimestampedModel):
    platform = models.CharField(max_length=40, default="wechat")
    product_type = models.CharField(max_length=40)
    media_type = models.CharField(max_length=20, blank=True)
    version = models.CharField(max_length=40)
    effective_at = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    source_url = models.URLField(blank=True)
    constraints = models.JSONField(default=dict)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-effective_at", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["platform", "product_type", "media_type", "version"],
                name="unique_platform_ruleset_version",
            )
        ]

    def __str__(self):
        suffix = f"/{self.media_type}" if self.media_type else ""
        return f"{self.platform}/{self.product_type}{suffix} {self.version}"
