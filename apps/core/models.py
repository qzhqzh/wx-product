import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class TimestampedModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ProductLine(TimestampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "已启用"
        PLANNED = "planned", "筹备中"
        PAUSED = "paused", "已暂停"

    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=240, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PLANNED)
    sort_order = models.PositiveSmallIntegerField(default=0)
    adapter_path = models.CharField(max_length=180, blank=True)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class IPCharacter(TimestampedModel):
    code = models.SlugField(max_length=60, unique=True)
    name = models.CharField(max_length=100)
    summary = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_characters",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class IPCharacterVersion(TimestampedModel):
    character = models.ForeignKey(
        IPCharacter, on_delete=models.CASCADE, related_name="versions"
    )
    version = models.PositiveIntegerField()
    personality = models.TextField(blank=True)
    style_anchors = models.JSONField(default=list, blank=True)
    forbidden_elements = models.JSONField(default=list, blank=True)
    palette = models.JSONField(default=list, blank=True)
    reference_notes = models.TextField(blank=True)
    is_locked = models.BooleanField(default=False)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_character_versions",
    )

    class Meta:
        ordering = ["character__name", "-version"]
        constraints = [
            models.UniqueConstraint(
                fields=["character", "version"], name="unique_character_version"
            )
        ]

    def __str__(self):
        return f"{self.character.name} v{self.version}"


class TrendTopic(TimestampedModel):
    class Risk(models.TextChoices):
        LOW = "low", "低"
        MEDIUM = "medium", "中"
        HIGH = "high", "高"

    title = models.CharField(max_length=160)
    source_url = models.URLField(blank=True)
    source_snapshot = models.TextField(blank=True)
    observed_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    risk_level = models.CharField(max_length=12, choices=Risk.choices, default=Risk.MEDIUM)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_trends",
    )

    class Meta:
        ordering = ["-observed_at"]

    def __str__(self):
        return self.title


class CreativeProject(TimestampedModel):
    class Lane(models.TextChoices):
        IP = "ip", "原创 IP"
        TREND = "trend", "热点快线"
        HYBRID = "hybrid", "IP × 热点"
        PRODUCT = "product", "产品研发"

    class Status(models.TextChoices):
        ACTIVE = "active", "生产中"
        PAUSED = "paused", "已暂停"
        COMPLETED = "completed", "已完成"
        ARCHIVED = "archived", "已归档"

    title = models.CharField(max_length=160)
    product_line = models.ForeignKey(
        ProductLine, on_delete=models.PROTECT, related_name="projects"
    )
    lane = models.CharField(max_length=12, choices=Lane.choices, default=Lane.IP)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="owned_creative_projects",
    )
    character_version = models.ForeignKey(
        IPCharacterVersion,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="projects",
    )
    trend_topic = models.ForeignKey(
        TrendTopic,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="projects",
    )
    due_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self):
        return self.title

    def clean(self):
        if self.lane == self.Lane.IP and not self.character_version_id:
            raise ValidationError({"character_version": "原创 IP 项目必须选择角色版本。"})
        if self.lane == self.Lane.TREND and not self.trend_topic_id:
            raise ValidationError({"trend_topic": "热点项目必须选择热点来源。"})
        if self.lane == self.Lane.HYBRID:
            if not self.character_version_id or not self.trend_topic_id:
                raise ValidationError("混合项目必须同时选择角色版本和热点来源。")


class TransitionEvent(TimestampedModel):
    object_type = models.CharField(max_length=60)
    object_id = models.UUIDField()
    from_state = models.CharField(max_length=40, blank=True)
    to_state = models.CharField(max_length=40)
    action = models.CharField(max_length=80)
    note = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pipeline_transition_events",
    )
    payload = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["object_type", "object_id", "-created_at"])]

    def __str__(self):
        return f"{self.object_type}: {self.from_state} → {self.to_state}"
