from django.conf import settings
from django.db import models

from apps.assets.models import AssetVersion, PlatformRuleSet
from apps.core.models import CreativeProject, TimestampedModel


class RedPacketCampaign(TimestampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        BRIEF_APPROVED = "brief_approved", "Brief 已确认"
        DESIGNING = "designing", "封面设计中"
        CREATIVE_REVIEW = "creative_review", "创意审稿"
        RIGHTS_REVIEW = "rights_review", "权利材料审核"
        QA_REVIEW = "qa_review", "质量与合规审核"
        EXPORT_READY = "export_ready", "可导出"
        SUBMITTED = "submitted", "已提交微信审核"
        APPROVED = "approved", "微信审核通过"
        DISTRIBUTING = "distributing", "发放中"
        COMPLETED = "completed", "发放完成"
        REWORK = "rework", "返修中"
        ARCHIVED = "archived", "已归档"

    project = models.ForeignKey(
        CreativeProject, on_delete=models.CASCADE, related_name="red_packet_campaigns"
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    audience = models.CharField(max_length=160, blank=True)
    cover_story = models.TextField(blank=True)
    greeting = models.CharField(max_length=120, blank=True)
    style_keywords = models.JSONField(default=list, blank=True)
    design_target = models.PositiveSmallIntegerField(default=3)
    planned_quantity = models.PositiveIntegerField(default=100)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    ruleset = models.ForeignKey(
        PlatformRuleSet,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="red_packet_campaigns",
    )
    preview_asset = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="red_packet_previews",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="owned_red_packet_campaigns",
    )

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.name

    @property
    def selected_design(self):
        return self.designs.filter(is_selected=True).select_related("asset").first()


class RedPacketDesign(TimestampedModel):
    campaign = models.ForeignKey(
        RedPacketCampaign, on_delete=models.CASCADE, related_name="designs"
    )
    order = models.PositiveSmallIntegerField()
    title = models.CharField(max_length=120)
    prompt = models.TextField(blank=True)
    asset = models.ForeignKey(
        AssetVersion, on_delete=models.PROTECT, related_name="red_packet_designs"
    )
    is_selected = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    review_note = models.TextField(blank=True)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "order"], name="unique_red_packet_design_order"
            ),
            models.UniqueConstraint(
                fields=["campaign"],
                condition=models.Q(is_selected=True),
                name="single_selected_red_packet_design",
            ),
        ]

    def __str__(self):
        return f"{self.campaign.name} #{self.order}"


class RedPacketValidationRun(TimestampedModel):
    campaign = models.ForeignKey(
        RedPacketCampaign, on_delete=models.CASCADE, related_name="validation_runs"
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
        related_name="created_red_packet_validations",
    )

    class Meta:
        ordering = ["-created_at"]


class RedPacketValidationIssue(TimestampedModel):
    class Severity(models.TextChoices):
        ERROR = "error", "错误"
        WARNING = "warning", "警告"

    run = models.ForeignKey(
        RedPacketValidationRun, on_delete=models.CASCADE, related_name="issues"
    )
    code = models.CharField(max_length=80)
    severity = models.CharField(max_length=12, choices=Severity.choices)
    message = models.CharField(max_length=300)
    remediation = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["severity", "code"]


class RedPacketApprovalRecord(TimestampedModel):
    class Decision(models.TextChoices):
        APPROVED = "approved", "通过"
        REJECTED = "rejected", "退回"

    campaign = models.ForeignKey(
        RedPacketCampaign, on_delete=models.CASCADE, related_name="approvals"
    )
    stage = models.CharField(max_length=40)
    decision = models.CharField(max_length=12, choices=Decision.choices)
    note = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="red_packet_approval_records",
    )

    class Meta:
        ordering = ["-created_at"]


class RedPacketExportBundle(TimestampedModel):
    campaign = models.ForeignKey(
        RedPacketCampaign, on_delete=models.CASCADE, related_name="exports"
    )
    ruleset = models.ForeignKey(PlatformRuleSet, on_delete=models.PROTECT)
    file = models.ForeignKey(
        AssetVersion, on_delete=models.PROTECT, related_name="red_packet_exports"
    )
    manifest = models.JSONField(default=dict)
    checksum_sha256 = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_red_packet_exports",
    )

    class Meta:
        ordering = ["-created_at"]


class RedPacketSubmission(TimestampedModel):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "已提交"
        IN_REVIEW = "in_review", "审核中"
        REJECTED = "rejected", "已驳回"
        APPROVED = "approved", "审核通过"

    campaign = models.ForeignKey(
        RedPacketCampaign, on_delete=models.CASCADE, related_name="submissions"
    )
    export_bundle = models.ForeignKey(
        RedPacketExportBundle, on_delete=models.PROTECT, related_name="submissions"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.SUBMITTED
    )
    platform_work_id = models.CharField(max_length=120, blank=True)
    submitted_at = models.DateTimeField()
    rejection_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="red_packet_submissions",
    )

    class Meta:
        ordering = ["-submitted_at"]


class RedPacketOrder(TimestampedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "待下单"
        PURCHASED = "purchased", "已下单"
        AVAILABLE = "available", "可发放"
        EXHAUSTED = "exhausted", "已用完"
        CANCELLED = "cancelled", "已取消"

    campaign = models.ForeignKey(
        RedPacketCampaign, on_delete=models.CASCADE, related_name="orders"
    )
    platform_order_no = models.CharField(max_length=120, blank=True)
    quantity = models.PositiveIntegerField()
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.PLANNED
    )
    purchased_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_red_packet_orders",
    )

    class Meta:
        ordering = ["-created_at"]

    @property
    def distributed_quantity(self):
        return sum(self.distributions.values_list("quantity", flat=True))

    @property
    def available_quantity(self):
        return max(0, self.quantity - self.distributed_quantity)


class RedPacketDistribution(TimestampedModel):
    order = models.ForeignKey(
        RedPacketOrder, on_delete=models.CASCADE, related_name="distributions"
    )
    channel = models.CharField(max_length=120)
    quantity = models.PositiveIntegerField()
    distributed_at = models.DateTimeField()
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_red_packet_distributions",
    )

    class Meta:
        ordering = ["-distributed_at"]
