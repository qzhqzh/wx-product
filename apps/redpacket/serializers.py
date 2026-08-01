from django.urls import reverse
from rest_framework import serializers

from apps.assets.serializers import AssetSerializer

from .models import (
    RedPacketCampaign,
    RedPacketDesign,
    RedPacketDistribution,
    RedPacketExportBundle,
    RedPacketOrder,
    RedPacketSubmission,
    RedPacketValidationIssue,
    RedPacketValidationRun,
)


class RedPacketDesignSerializer(serializers.ModelSerializer):
    asset = AssetSerializer(read_only=True)

    class Meta:
        model = RedPacketDesign
        fields = (
            "id",
            "order",
            "title",
            "prompt",
            "asset",
            "is_selected",
            "is_approved",
            "review_note",
        )


class RedPacketValidationIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = RedPacketValidationIssue
        fields = ("id", "code", "severity", "message", "remediation")


class RedPacketValidationRunSerializer(serializers.ModelSerializer):
    issues = RedPacketValidationIssueSerializer(many=True, read_only=True)

    class Meta:
        model = RedPacketValidationRun
        fields = (
            "id",
            "passed",
            "error_count",
            "warning_count",
            "summary",
            "issues",
            "created_at",
        )


class RedPacketExportSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = RedPacketExportBundle
        fields = (
            "id",
            "checksum_sha256",
            "manifest",
            "download_url",
            "created_at",
        )

    def get_download_url(self, obj):
        return reverse("download-red-packet-export", kwargs={"export_id": obj.pk})


class RedPacketSubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RedPacketSubmission
        fields = (
            "id",
            "status",
            "platform_work_id",
            "submitted_at",
            "rejection_reason",
            "notes",
            "created_at",
        )


class RedPacketDistributionSerializer(serializers.ModelSerializer):
    class Meta:
        model = RedPacketDistribution
        fields = ("id", "channel", "quantity", "distributed_at", "notes")


class RedPacketOrderSerializer(serializers.ModelSerializer):
    distributions = RedPacketDistributionSerializer(many=True, read_only=True)
    distributed_quantity = serializers.IntegerField(read_only=True)
    available_quantity = serializers.IntegerField(read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = RedPacketOrder
        fields = (
            "id",
            "platform_order_no",
            "quantity",
            "unit_cost",
            "status",
            "status_label",
            "purchased_at",
            "expires_at",
            "notes",
            "distributed_quantity",
            "available_quantity",
            "distributions",
        )


class RedPacketCampaignSerializer(serializers.ModelSerializer):
    designs = RedPacketDesignSerializer(many=True, read_only=True)
    preview_asset = AssetSerializer(read_only=True)
    latest_validation = serializers.SerializerMethodField()
    latest_export = serializers.SerializerMethodField()
    latest_submission = serializers.SerializerMethodField()
    orders = RedPacketOrderSerializer(many=True, read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = RedPacketCampaign
        fields = (
            "id",
            "name",
            "description",
            "audience",
            "cover_story",
            "greeting",
            "style_keywords",
            "design_target",
            "planned_quantity",
            "status",
            "status_label",
            "preview_asset",
            "designs",
            "latest_validation",
            "latest_export",
            "latest_submission",
            "orders",
            "updated_at",
        )

    def get_latest_validation(self, obj):
        run = obj.validation_runs.prefetch_related("issues").first()
        return RedPacketValidationRunSerializer(run).data if run else None

    def get_latest_export(self, obj):
        bundle = obj.exports.first()
        return RedPacketExportSerializer(bundle).data if bundle else None

    def get_latest_submission(self, obj):
        submission = obj.submissions.first()
        return RedPacketSubmissionSerializer(submission).data if submission else None
