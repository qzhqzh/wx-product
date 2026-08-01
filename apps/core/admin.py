from django.contrib import admin

from .models import (
    CreativeProject,
    IPCharacter,
    IPCharacterVersion,
    ProductLine,
    TransitionEvent,
    TrendTopic,
)


@admin.register(ProductLine)
class ProductLineAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "status", "sort_order")
    list_filter = ("status",)
    search_fields = ("name", "code")


class IPCharacterVersionInline(admin.TabularInline):
    model = IPCharacterVersion
    extra = 0


@admin.register(IPCharacter)
class IPCharacterAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active", "updated_at")
    inlines = [IPCharacterVersionInline]


@admin.register(TrendTopic)
class TrendTopicAdmin(admin.ModelAdmin):
    list_display = ("title", "risk_level", "observed_at", "expires_at")
    list_filter = ("risk_level",)


@admin.register(CreativeProject)
class CreativeProjectAdmin(admin.ModelAdmin):
    list_display = ("title", "product_line", "lane", "status", "owner", "updated_at")
    list_filter = ("product_line", "lane", "status")
    search_fields = ("title", "description")


@admin.register(TransitionEvent)
class TransitionEventAdmin(admin.ModelAdmin):
    list_display = ("object_type", "object_id", "from_state", "to_state", "actor", "created_at")
    readonly_fields = [field.name for field in TransitionEvent._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
