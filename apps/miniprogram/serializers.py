from django.urls import reverse
from rest_framework import serializers

from apps.assets.serializers import AssetSerializer

from .models import (
    MiniProgramArtifact,
    MiniProgramChecklistItem,
    MiniProgramExportBundle,
    MiniProgramRelease,
    MiniProgramSubmission,
    MiniProgramTestCase,
    MiniProgramValidationIssue,
    MiniProgramValidationRun,
)


class MiniProgramArtifactSerializer(serializers.ModelSerializer):
    asset = AssetSerializer(read_only=True)
    artifact_type_label = serializers.CharField(
        source="get_artifact_type_display", read_only=True
    )

    class Meta:
        model = MiniProgramArtifact
        fields = (
            "id",
            "artifact_type",
            "artifact_type_label",
            "label",
            "asset",
            "is_current",
            "notes",
        )


class MiniProgramChecklistSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = MiniProgramChecklistItem
        fields = (
            "id",
            "category",
            "category_label",
            "title",
            "is_required",
            "is_completed",
            "note",
            "evidence_asset_id",
        )


class MiniProgramTestCaseSerializer(serializers.ModelSerializer):
    result_label = serializers.CharField(source="get_result_display", read_only=True)

    class Meta:
        model = MiniProgramTestCase
        fields = (
            "id",
            "name",
            "steps",
            "expected_result",
            "actual_result",
            "result",
            "result_label",
            "evidence_asset_id",
            "executed_at",
        )


class MiniProgramValidationIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = MiniProgramValidationIssue
        fields = ("id", "code", "severity", "message", "remediation")


class MiniProgramValidationRunSerializer(serializers.ModelSerializer):
    issues = MiniProgramValidationIssueSerializer(many=True, read_only=True)

    class Meta:
        model = MiniProgramValidationRun
        fields = (
            "id",
            "passed",
            "error_count",
            "warning_count",
            "summary",
            "issues",
            "created_at",
        )


class MiniProgramExportSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = MiniProgramExportBundle
        fields = (
            "id",
            "checksum_sha256",
            "manifest",
            "download_url",
            "created_at",
        )

    def get_download_url(self, obj):
        return reverse("download-mini-program-export", kwargs={"export_id": obj.pk})


class MiniProgramSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MiniProgramSubmission
        fields = (
            "id",
            "status",
            "platform_audit_id",
            "submitted_at",
            "released_at",
            "rejection_reason",
            "notes",
            "created_at",
        )


class MiniProgramReleaseSerializer(serializers.ModelSerializer):
    artifacts = MiniProgramArtifactSerializer(many=True, read_only=True)
    checklist_items = MiniProgramChecklistSerializer(many=True, read_only=True)
    test_cases = MiniProgramTestCaseSerializer(many=True, read_only=True)
    latest_validation = serializers.SerializerMethodField()
    latest_export = serializers.SerializerMethodField()
    latest_submission = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    release_type_label = serializers.CharField(
        source="get_release_type_display", read_only=True
    )

    class Meta:
        model = MiniProgramRelease
        fields = (
            "id",
            "name",
            "app_id",
            "version",
            "release_type",
            "release_type_label",
            "status",
            "status_label",
            "prd_summary",
            "change_log",
            "privacy_summary",
            "service_category",
            "artifacts",
            "checklist_items",
            "test_cases",
            "latest_validation",
            "latest_export",
            "latest_submission",
            "updated_at",
        )

    def get_latest_validation(self, obj):
        run = obj.validation_runs.prefetch_related("issues").first()
        return MiniProgramValidationRunSerializer(run).data if run else None

    def get_latest_export(self, obj):
        bundle = obj.exports.first()
        return MiniProgramExportSerializer(bundle).data if bundle else None

    def get_latest_submission(self, obj):
        submission = obj.submissions.first()
        return MiniProgramSubmissionSerializer(submission).data if submission else None
