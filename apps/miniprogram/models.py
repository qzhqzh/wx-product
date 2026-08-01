from django.conf import settings
from django.db import models

from apps.assets.models import AssetVersion, PlatformRuleSet
from apps.core.models import CreativeProject, TimestampedModel


class MiniProgramRelease(TimestampedModel):
    class ReleaseType(models.TextChoices):
        FEATURE = "feature", "功能版本"
        HOTFIX = "hotfix", "紧急修复"
        INITIAL = "initial", "首次发布"

    class Status(models.TextChoices):
        DRAFT = "draft", "草稿"
        PRD_APPROVED = "prd_approved", "PRD 已确认"
        DEVELOPING = "developing", "开发中"
        BUILD_READY = "build_ready", "构建已就绪"
        EXPERIENCE_REVIEW = "experience_review", "体验版验收"
        COMPLIANCE_REVIEW = "compliance_review", "隐私与合规审核"
        QA_REVIEW = "qa_review", "发布 QA"
        EXPORT_READY = "export_ready", "审核包可导出"
        SUBMITTED = "submitted", "已提交微信审核"
        APPROVED = "approved", "微信审核通过"
        RELEASED = "released", "已发布"
        REWORK = "rework", "返修中"
        ARCHIVED = "archived", "已归档"

    project = models.ForeignKey(
        CreativeProject, on_delete=models.CASCADE, related_name="mini_program_releases"
    )
    name = models.CharField(max_length=120)
    app_id = models.CharField(max_length=80, blank=True)
    version = models.CharField(max_length=40)
    release_type = models.CharField(
        max_length=12, choices=ReleaseType.choices, default=ReleaseType.FEATURE
    )
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.DRAFT)
    prd_summary = models.TextField(blank=True)
    change_log = models.TextField(blank=True)
    privacy_summary = models.TextField(blank=True)
    service_category = models.CharField(max_length=120, blank=True)
    ruleset = models.ForeignKey(
        PlatformRuleSet,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="mini_program_releases",
    )
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="owned_mini_program_releases",
    )

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "version"], name="unique_project_mini_program_version"
            )
        ]

    def __str__(self):
        return f"{self.name} {self.version}"


class MiniProgramArtifact(TimestampedModel):
    class ArtifactType(models.TextChoices):
        BUILD_PACKAGE = "build_package", "构建包"
        EXPERIENCE_QR = "experience_qr", "体验二维码"
        SCREENSHOT = "screenshot", "页面截图"
        PRIVACY_DOCUMENT = "privacy_document", "隐私说明"
        TEST_EVIDENCE = "test_evidence", "测试证据"

    release = models.ForeignKey(
        MiniProgramRelease, on_delete=models.CASCADE, related_name="artifacts"
    )
    artifact_type = models.CharField(max_length=24, choices=ArtifactType.choices)
    label = models.CharField(max_length=120)
    asset = models.ForeignKey(
        AssetVersion, on_delete=models.PROTECT, related_name="mini_program_artifacts"
    )
    is_current = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["artifact_type", "-created_at"]

    def __str__(self):
        return f"{self.release} · {self.get_artifact_type_display()}"


class MiniProgramChecklistItem(TimestampedModel):
    class Category(models.TextChoices):
        PRD = "prd", "产品范围"
        BUILD = "build", "构建配置"
        FUNCTIONAL = "functional", "功能验收"
        PRIVACY = "privacy", "隐私合规"
        SECURITY = "security", "安全检查"
        PLATFORM = "platform", "微信平台资料"

    release = models.ForeignKey(
        MiniProgramRelease, on_delete=models.CASCADE, related_name="checklist_items"
    )
    category = models.CharField(max_length=16, choices=Category.choices)
    title = models.CharField(max_length=180)
    is_required = models.BooleanField(default=True)
    is_completed = models.BooleanField(default=False)
    note = models.TextField(blank=True)
    evidence_asset = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mini_program_checklist_evidence",
    )

    class Meta:
        ordering = ["category", "created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["release", "category", "title"],
                name="unique_mini_program_checklist_item",
            )
        ]


class MiniProgramTestCase(TimestampedModel):
    class Result(models.TextChoices):
        PENDING = "pending", "待执行"
        PASSED = "passed", "通过"
        FAILED = "failed", "失败"
        BLOCKED = "blocked", "阻塞"

    release = models.ForeignKey(
        MiniProgramRelease, on_delete=models.CASCADE, related_name="test_cases"
    )
    name = models.CharField(max_length=180)
    steps = models.JSONField(default=list)
    expected_result = models.TextField()
    actual_result = models.TextField(blank=True)
    result = models.CharField(
        max_length=12, choices=Result.choices, default=Result.PENDING
    )
    evidence_asset = models.ForeignKey(
        AssetVersion,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mini_program_test_evidence",
    )
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="executed_mini_program_tests",
    )
    executed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["release", "name"], name="unique_mini_program_test_case"
            )
        ]


class MiniProgramValidationRun(TimestampedModel):
    release = models.ForeignKey(
        MiniProgramRelease, on_delete=models.CASCADE, related_name="validation_runs"
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
        related_name="created_mini_program_validations",
    )

    class Meta:
        ordering = ["-created_at"]


class MiniProgramValidationIssue(TimestampedModel):
    class Severity(models.TextChoices):
        ERROR = "error", "错误"
        WARNING = "warning", "警告"

    run = models.ForeignKey(
        MiniProgramValidationRun, on_delete=models.CASCADE, related_name="issues"
    )
    code = models.CharField(max_length=80)
    severity = models.CharField(max_length=12, choices=Severity.choices)
    message = models.CharField(max_length=300)
    remediation = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["severity", "code"]


class MiniProgramApprovalRecord(TimestampedModel):
    class Decision(models.TextChoices):
        APPROVED = "approved", "通过"
        REJECTED = "rejected", "退回"

    release = models.ForeignKey(
        MiniProgramRelease, on_delete=models.CASCADE, related_name="approvals"
    )
    stage = models.CharField(max_length=40)
    decision = models.CharField(max_length=12, choices=Decision.choices)
    note = models.TextField(blank=True)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="mini_program_approval_records",
    )

    class Meta:
        ordering = ["-created_at"]


class MiniProgramExportBundle(TimestampedModel):
    release = models.ForeignKey(
        MiniProgramRelease, on_delete=models.CASCADE, related_name="exports"
    )
    ruleset = models.ForeignKey(PlatformRuleSet, on_delete=models.PROTECT)
    file = models.ForeignKey(
        AssetVersion, on_delete=models.PROTECT, related_name="mini_program_exports"
    )
    manifest = models.JSONField(default=dict)
    checksum_sha256 = models.CharField(max_length=64)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="created_mini_program_exports",
    )

    class Meta:
        ordering = ["-created_at"]


class MiniProgramSubmission(TimestampedModel):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "已提交"
        IN_REVIEW = "in_review", "审核中"
        REJECTED = "rejected", "已驳回"
        APPROVED = "approved", "审核通过"
        RELEASED = "released", "已发布"

    release = models.ForeignKey(
        MiniProgramRelease, on_delete=models.CASCADE, related_name="submissions"
    )
    export_bundle = models.ForeignKey(
        MiniProgramExportBundle, on_delete=models.PROTECT, related_name="submissions"
    )
    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.SUBMITTED
    )
    platform_audit_id = models.CharField(max_length=120, blank=True)
    submitted_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="mini_program_submissions",
    )

    class Meta:
        ordering = ["-submitted_at"]
