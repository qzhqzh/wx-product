from django.conf import settings
from django.db import models, transaction

from apps.assets.models import AssetVersion, PlatformRuleSet
from apps.core.models import CreativeProject, TimestampedModel


class PromptPreset(TimestampedModel):
    class Category(models.TextChoices):
        BASE = "base", "基础"
        STYLE = "style", "风格"
        COMPOSITION = "composition", "构图"
        QUALITY = "quality", "质量"
        NEGATIVE = "negative", "负向"

    name = models.CharField(max_length=120)
    category = models.CharField(max_length=20, choices=Category.choices)
    description = models.CharField(max_length=240, blank=True)
    content = models.TextField()
    is_default = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_prompt_presets",
    )

    class Meta:
        ordering = ["category", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["category", "name"],
                name="unique_prompt_preset_name_per_category",
            ),
        ]

    def __str__(self):
        return f"{self.get_category_display()} · {self.name}"

    def save(self, *args, **kwargs):
        if not self.is_default:
            return super().save(*args, **kwargs)
        with transaction.atomic():
            type(self).objects.filter(
                category=self.category,
                is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)
            return super().save(*args, **kwargs)


class EmojiPack(TimestampedModel):
    class PackType(models.TextChoices):
        ALBUM = "album", "表情专辑"
        SINGLE = "single", "表情单品"

    class MediaType(models.TextChoices):
        STATIC = "static", "静态 PNG"
        DYNAMIC = "dynamic", "动态 GIF"

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        BRIEF_APPROVED = "brief_approved", "Brief 已确认"
        GENERATING = "generating", "生成中"
        CREATIVE_REVIEW = "creative_review", "创意审稿"
        PROCESSING = "processing", "素材处理中"
        QA_REVIEW = "qa_review", "质量与合规审核"
        EXPORT_READY = "export_ready", "可导出"
        SUBMITTED = "submitted", "已投稿"
        PUBLISHED = "published", "已上架"
        REWORK = "rework", "返修中"
        ARCHIVED = "archived", "已归档"

    project = models.ForeignKey(
        CreativeProject, on_delete=models.CASCADE, related_name="emoji_packs"
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    pack_type = models.CharField(
        max_length=12, choices=PackType.choices, default=PackType.ALBUM
    )
    media_type = models.CharField(
        max_length=12, choices=MediaType.choices, default=MediaType.STATIC
    )
    target_count = models.PositiveSmallIntegerField(default=8)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    audience = models.CharField(max_length=160, blank=True)
    tone = models.CharField(max_length=160, blank=True)
    creative_brief = models.TextField(blank=True)
    negative_prompt = models.TextField(blank=True)
    prompt_presets = models.ManyToManyField(
        PromptPreset,
        blank=True,
        related_name="emoji_packs",
    )
    ruleset = models.ForeignKey(
        PlatformRuleSet,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="emoji_packs",
    )
    cover_asset = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cover_for_packs",
    )
    icon_asset = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="icon_for_packs",
    )
    banner_asset = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="banner_for_packs",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="owned_emoji_packs",
    )

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name

    @property
    def selected_count(self):
        return self.items.exclude(selected_asset=None).count()


class EmojiItem(TimestampedModel):
    pack = models.ForeignKey(EmojiPack, on_delete=models.CASCADE, related_name="items")
    order = models.PositiveSmallIntegerField()
    meaning = models.CharField(max_length=40)
    copy_text = models.CharField(max_length=80, blank=True)
    action = models.CharField(max_length=160, blank=True)
    prompt = models.TextField(blank=True)
    review_note = models.TextField(blank=True)
    is_approved = models.BooleanField(default=False)
    candidates = models.ManyToManyField(
        AssetVersion, blank=True, related_name="candidate_for_emoji_items"
    )
    selected_asset = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="selected_for_emoji_items",
    )

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(fields=["pack", "order"], name="unique_pack_item_order")
        ]

    def __str__(self):
        return f"{self.pack.name} #{self.order} {self.meaning}"


class AnimationSequence(TimestampedModel):
    item = models.OneToOneField(
        EmojiItem, on_delete=models.CASCADE, related_name="animation_sequence"
    )
    loop_count = models.PositiveSmallIntegerField(default=0, help_text="0 表示无限循环")
    output_asset = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="animation_sequence_outputs",
    )
    status = models.CharField(max_length=20, default="draft")


class AnimationFrame(TimestampedModel):
    sequence = models.ForeignKey(
        AnimationSequence, on_delete=models.CASCADE, related_name="frames"
    )
    order = models.PositiveSmallIntegerField()
    duration_ms = models.PositiveIntegerField(default=120)
    asset = models.ForeignKey(
        AssetVersion, on_delete=models.PROTECT, related_name="animation_frames"
    )

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["sequence", "order"], name="unique_sequence_frame_order"
            )
        ]


class PromptTemplateVersion(TimestampedModel):
    code = models.SlugField(max_length=80)
    version = models.PositiveIntegerField()
    purpose = models.CharField(max_length=120)
    template = models.TextField()
    response_schema = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["code", "version"], name="unique_prompt_template_version"
            )
        ]


class GenerationJob(TimestampedModel):
    class JobType(models.TextChoices):
        PLAN = "plan", "语义策划"
        PROMPT = "prompt", "提示词优化"
        IMAGE = "image", "图像生成"
        FRAME = "frame", "序列帧生成"
        ASSEMBLE = "assemble", "动图合成"
        EXPORT = "export", "投稿包导出"

    class Status(models.TextChoices):
        QUEUED = "queued", "排队中"
        RUNNING = "running", "执行中"
        SUCCEEDED = "succeeded", "已完成"
        FAILED = "failed", "失败"
        BLOCKED = "blocked", "等待外部配置"
        CANCELLED = "cancelled", "已取消"

    pack = models.ForeignKey(
        EmojiPack, on_delete=models.CASCADE, related_name="generation_jobs"
    )
    item = models.ForeignKey(
        EmojiItem,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="generation_jobs",
    )
    job_type = models.CharField(max_length=20, choices=JobType.choices)
    provider = models.CharField(max_length=40)
    model = models.CharField(max_length=100, blank=True)
    prompt_template = models.ForeignKey(
        PromptTemplateVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jobs",
    )
    prompt = models.TextField(blank=True)
    input_payload = models.JSONField(default=dict, blank=True)
    output_payload = models.JSONField(default=dict, blank=True)
    idempotency_key = models.CharField(max_length=160, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.QUEUED)
    attempts = models.PositiveSmallIntegerField(default=0)
    external_job_id = models.CharField(max_length=160, blank=True)
    error_code = models.CharField(max_length=80, blank=True)
    error_message = models.TextField(blank=True)
    usage = models.JSONField(default=dict, blank=True)
    estimated_cost = models.DecimalField(
        max_digits=12, decimal_places=4, null=True, blank=True
    )
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_generation_jobs",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status", "job_type", "-created_at"])]


class ValidationRun(TimestampedModel):
    pack = models.ForeignKey(
        EmojiPack, on_delete=models.CASCADE, related_name="validation_runs"
    )
    ruleset = models.ForeignKey(PlatformRuleSet, on_delete=models.PROTECT)
    passed = models.BooleanField(default=False)
    error_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_validation_runs",
    )

    class Meta:
        ordering = ["-created_at"]


class ValidationIssue(TimestampedModel):
    class Severity(models.TextChoices):
        ERROR = "error", "错误"
        WARNING = "warning", "警告"

    run = models.ForeignKey(ValidationRun, on_delete=models.CASCADE, related_name="issues")
    item = models.ForeignKey(
        EmojiItem,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="validation_issues",
    )
    asset = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="validation_issues",
    )
    code = models.CharField(max_length=80)
    severity = models.CharField(max_length=12, choices=Severity.choices)
    message = models.CharField(max_length=300)
    remediation = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["severity", "code"]


class ApprovalRecord(TimestampedModel):
    class Decision(models.TextChoices):
        APPROVED = "approved", "通过"
        REJECTED = "rejected", "退回"

    pack = models.ForeignKey(
        EmojiPack, on_delete=models.CASCADE, related_name="approvals"
    )
    stage = models.CharField(max_length=40)
    decision = models.CharField(max_length=12, choices=Decision.choices)
    note = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="emoji_approval_records",
    )

    class Meta:
        ordering = ["-created_at"]


class ExportBundle(TimestampedModel):
    pack = models.ForeignKey(EmojiPack, on_delete=models.CASCADE, related_name="exports")
    ruleset = models.ForeignKey(PlatformRuleSet, on_delete=models.PROTECT)
    file = models.ForeignKey(
        AssetVersion, on_delete=models.PROTECT, related_name="export_bundles"
    )
    manifest = models.JSONField(default=dict)
    checksum_sha256 = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_export_bundles",
    )

    class Meta:
        ordering = ["-created_at"]


class SubmissionRecord(TimestampedModel):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "已提交"
        IN_REVIEW = "in_review", "审核中"
        REJECTED = "rejected", "已驳回"
        APPROVED = "approved", "审核通过"
        PUBLISHED = "published", "已上架"

    pack = models.ForeignKey(
        EmojiPack, on_delete=models.CASCADE, related_name="submissions"
    )
    export_bundle = models.ForeignKey(
        ExportBundle,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="submissions",
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.SUBMITTED
    )
    platform_work_id = models.CharField(max_length=120, blank=True)
    submitted_at = models.DateTimeField()
    scheduled_publish_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="emoji_submission_records",
    )

    class Meta:
        ordering = ["-submitted_at"]


class MetricSnapshot(TimestampedModel):
    pack = models.ForeignKey(
        EmojiPack, on_delete=models.CASCADE, related_name="metric_snapshots"
    )
    captured_on = models.DateField()
    source = models.CharField(max_length=120, default="manual")
    metrics = models.JSONField(default=dict)
    source_attachment = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="metric_snapshots",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_metric_snapshots",
    )

    class Meta:
        ordering = ["-captured_on"]
        constraints = [
            models.UniqueConstraint(
                fields=["pack", "captured_on", "source"],
                name="unique_pack_metric_snapshot",
            )
        ]
