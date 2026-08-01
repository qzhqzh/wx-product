from django.core.exceptions import PermissionDenied
from django.http import FileResponse
from django.shortcuts import get_object_or_404

from apps.assets.models import AssetVersion

from .media_hardening import canonical_mime_for_asset, is_safe_inline_asset

SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
WRITE_ROLE_RULES = {
    ("apps.core.views", "project_create"): {"creator", "planner", "admin"},
    ("apps.core.views", "pack_create"): {"creator", "planner", "admin"},
    ("apps.emoji.views", "pack_create"): {"creator", "planner", "admin"},
    ("apps.emoji.views", "prompt_preset_create"): {"creator", "planner", "admin"},
    ("apps.emoji.views", "prompt_preset_update"): {"creator", "planner", "admin"},
    ("apps.emoji.views", "prompt_preset_toggle"): {"creator", "planner", "admin"},
    ("apps.redpacket.views", "campaign_create"): {"creator", "planner", "admin"},
    ("apps.miniprogram.views", "release_create"): {"creator", "planner", "admin"},
}


class PipelineSecurityMiddleware:
    """Apply consistent role checks and serve assets with safe response headers."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        view_key = (view_func.__module__, view_func.__name__)

        if view_key == ("apps.core.views", "view_asset"):
            if not request.user.is_authenticated:
                return None
            asset = get_object_or_404(AssetVersion, pk=view_kwargs["asset_id"])
            inline = is_safe_inline_asset(asset)
            response = FileResponse(
                asset.file.open("rb"),
                as_attachment=not inline,
                filename=asset.original_name or None,
                content_type=canonical_mime_for_asset(asset),
            )
            response["Cache-Control"] = "private, max-age=300"
            response["X-Content-Type-Options"] = "nosniff"
            if not inline:
                response["Content-Security-Policy"] = "default-src 'none'; sandbox"
            return response

        if request.method in SAFE_METHODS or not request.user.is_authenticated:
            return None
        roles = WRITE_ROLE_RULES.get(view_key)
        if roles is None or request.user.is_superuser:
            return None
        if not request.user.groups.filter(name__in=roles).exists():
            raise PermissionDenied("当前账号没有执行该操作的流水线角色。")
        return None
