from django.contrib import admin

from .models import (
    AnimationFrame,
    AnimationSequence,
    ApprovalRecord,
    EmojiItem,
    EmojiPack,
    ExportBundle,
    GenerationJob,
    MetricSnapshot,
    PromptPreset,
    PromptTemplateVersion,
    SubmissionRecord,
    ValidationIssue,
    ValidationRun,
)


class EmojiItemInline(admin.TabularInline):
    model = EmojiItem
    extra = 0
    fields = ("order", "meaning", "copy_text", "is_approved", "selected_asset")


@admin.register(EmojiPack)
class EmojiPackAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "project",
        "pack_type",
        "media_type",
        "target_count",
        "status",
        "updated_at",
    )
    list_filter = ("pack_type", "media_type", "status")
    search_fields = ("name", "project__title")
    inlines = [EmojiItemInline]


@admin.register(GenerationJob)
class GenerationJobAdmin(admin.ModelAdmin):
    list_display = ("job_type", "pack", "provider", "model", "status", "created_at")
    list_filter = ("job_type", "provider", "status")
    readonly_fields = ("idempotency_key", "usage", "output_payload", "error_message")


admin.site.register(AnimationSequence)
admin.site.register(AnimationFrame)
admin.site.register(PromptPreset)
admin.site.register(PromptTemplateVersion)
admin.site.register(ValidationRun)
admin.site.register(ValidationIssue)
admin.site.register(ApprovalRecord)
admin.site.register(ExportBundle)
admin.site.register(SubmissionRecord)
admin.site.register(MetricSnapshot)
