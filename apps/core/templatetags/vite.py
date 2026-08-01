import hashlib
import json
from functools import lru_cache

from django import template
from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage

register = template.Library()


@lru_cache(maxsize=1)
def _manifest():
    path = settings.BASE_DIR / "static" / "dist" / ".vite" / "manifest.json"
    try:
        return json.loads(path.read_text())
    except FileNotFoundError as exc:
        raise RuntimeError("Vite manifest 缺失，请先运行 `bun run build`。") from exc


@register.simple_tag
def vite_asset(entry: str, asset_type: str = "js"):
    bundle = _manifest()[entry]
    if asset_type == "css":
        files = bundle.get("css", [])
        if not files:
            return ""
        filename = files[0]
    else:
        filename = bundle["file"]
    return staticfiles_storage.url(f"dist/{filename}")


@register.simple_tag
def static_versioned(path: str):
    source = settings.BASE_DIR / "static" / path
    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:12]
    return f"{staticfiles_storage.url(path)}?v={digest}"
