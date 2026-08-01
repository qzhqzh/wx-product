from rest_framework import serializers

from apps.assets.serializers import AssetSerializer

from .models import (
    AnimationFrame,
    EmojiItem,
    EmojiPack,
    ExportBundle,
    GenerationJob,
    PromptPreset,
    SubmissionRecord,
    ValidationIssue,
    ValidationRun,
)


class PromptPresetSerializer(serializers.ModelSerializer):
    category_label = serializers.CharField(source="get_category_display", read_only=True)

    class Meta:
        model = PromptPreset
        fields = (
            "id",
            "name",
            "category",
            "category_label",
            "description",
            "content",
            "is_default",
        )


class AnimationFrameSerializer(serializers.ModelSerializer):
    asset = AssetSerializer(read_only=True)

    class Meta:
        model = AnimationFrame
        fields = ("id", "order", "duration_ms", "asset")


class EmojiItemSerializer(serializers.ModelSerializer):
    candidates = AssetSerializer(many=True, read_only=True)
    selected_asset = AssetSerializer(read_only=True)
    frames = serializers.SerializerMethodField()

    class Meta:
        model = EmojiItem
        fields = (
            "id",
            "order",
            "meaning",
            "copy_text",
            "action",
            "prompt",
            "review_note",
            "is_approved",
            "candidates",
            "selected_asset",
            "frames",
        )

    def get_frames(self, obj):
        sequence = getattr(obj, "animation_sequence", None)
        if not sequence:
            return []
        return AnimationFrameSerializer(sequence.frames.select_related("asset"), many=True).data


class JobSerializer(serializers.ModelSerializer):
    job_type_label = serializers.CharField(source="get_job_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = GenerationJob
        fields = (
            "id",
            "item_id",
            "job_type",
            "job_type_label",
            "provider",
            "model",
            "status",
            "status_label",
            "attempts",
            "error_code",
            "error_message",
            "output_payload",
            "created_at",
            "started_at",
            "completed_at",
        )


class ValidationIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = ValidationIssue
        fields = (
            "id",
            "item_id",
            "asset_id",
            "code",
            "severity",
            "message",
            "remediation",
        )


class ValidationRunSerializer(serializers.ModelSerializer):
    issues = ValidationIssueSerializer(many=True, read_only=True)

    class Meta:
        model = ValidationRun
        fields = (
            "id",
            "passed",
            "error_count",
            "warning_count",
            "summary",
            "issues",
            "created_at",
        )


class ExportBundleSerializer(serializers.ModelSerializer):
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ExportBundle
        fields = (
            "id",
            "checksum_sha256",
            "manifest",
            "download_url",
            "created_at",
        )

    def get_download_url(self, obj):
        from django.urls import reverse

        return reverse("download-export", kwargs={"export_id": obj.pk})


class SubmissionSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubmissionRecord
        fields = (
            "id",
            "export_bundle",
            "status",
            "platform_work_id",
            "submitted_at",
            "scheduled_publish_at",
            "rejection_reason",
            "notes",
            "created_at",
        )


class PackSerializer(serializers.ModelSerializer):
    items = EmojiItemSerializer(many=True, read_only=True)
    jobs = serializers.SerializerMethodField()
    latest_validation = serializers.SerializerMethodField()
    latest_export = serializers.SerializerMethodField()
    latest_submission = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    media_type_label = serializers.CharField(source="get_media_type_display", read_only=True)
    cover_asset = AssetSerializer(read_only=True)
    icon_asset = AssetSerializer(read_only=True)
    banner_asset = AssetSerializer(read_only=True)
    prompt_presets = PromptPresetSerializer(many=True, read_only=True)
    available_prompt_presets = serializers.SerializerMethodField()

    class Meta:
        model = EmojiPack
        fields = (
            "id",
            "name",
            "description",
            "pack_type",
            "media_type",
            "media_type_label",
            "target_count",
            "status",
            "status_label",
            "audience",
            "tone",
            "creative_brief",
            "negative_prompt",
            "prompt_presets",
            "available_prompt_presets",
            "cover_asset",
            "icon_asset",
            "banner_asset",
            "items",
            "jobs",
            "latest_validation",
            "latest_export",
            "latest_submission",
            "updated_at",
        )

    def get_jobs(self, obj):
        return JobSerializer(obj.generation_jobs.order_by("-created_at")[:30], many=True).data

    def get_available_prompt_presets(self, obj):
        selected_ids = {
            str(preset_id) for preset_id in obj.prompt_presets.values_list("id", flat=True)
        }
        data = PromptPresetSerializer(
            PromptPreset.objects.filter(is_active=True),
            many=True,
        ).data
        for preset in data:
            preset["selected"] = preset["id"] in selected_ids
        return data

    def get_latest_validation(self, obj):
        run = obj.validation_runs.prefetch_related("issues").first()
        return ValidationRunSerializer(run).data if run else None

    def get_latest_export(self, obj):
        bundle = obj.exports.first()
        return ExportBundleSerializer(bundle).data if bundle else None

    def get_latest_submission(self, obj):
        submission = obj.submissions.first()
        return SubmissionSerializer(submission).data if submission else None
