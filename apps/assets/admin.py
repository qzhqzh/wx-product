from django.contrib import admin

from .models import AssetVersion, PlatformRuleSet, RightsEvidence


@admin.register(AssetVersion)
class AssetVersionAdmin(admin.ModelAdmin):
    list_display = (
        "original_name",
        "kind",
        "source",
        "width",
        "height",
        "size_bytes",
        "created_at",
    )
    list_filter = ("kind", "source")
    search_fields = ("original_name", "checksum_sha256")
    readonly_fields = (
        "checksum_sha256",
        "size_bytes",
        "width",
        "height",
        "frame_count",
        "duration_ms",
    )


admin.site.register(RightsEvidence)


@admin.register(PlatformRuleSet)
class PlatformRuleSetAdmin(admin.ModelAdmin):
    list_display = (
        "platform",
        "product_type",
        "media_type",
        "version",
        "is_active",
        "effective_at",
    )
    list_filter = ("platform", "product_type", "media_type", "is_active")
