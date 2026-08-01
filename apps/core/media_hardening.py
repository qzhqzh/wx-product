import io
import sys
import warnings
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, UnidentifiedImageError

from apps.assets.models import AssetVersion


class AssetValidationError(ValueError):
    """Raised when uploaded or generated media exceeds the processing budget."""


IMAGE_KINDS = {
    AssetVersion.Kind.SOURCE,
    AssetVersion.Kind.REFERENCE,
    AssetVersion.Kind.CANDIDATE,
    AssetVersion.Kind.FINAL_STATIC,
    AssetVersion.Kind.ANIMATION_FRAME,
    AssetVersion.Kind.FINAL_GIF,
    AssetVersion.Kind.COVER,
    AssetVersion.Kind.ICON,
    AssetVersion.Kind.BANNER,
    AssetVersion.Kind.RED_PACKET_COVER,
    AssetVersion.Kind.RED_PACKET_PREVIEW,
    AssetVersion.Kind.EXPERIENCE_QR,
    AssetVersion.Kind.SCREENSHOT,
}

IMAGE_MIME_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "GIF": "image/gif",
    "WEBP": "image/webp",
}

IMAGE_EXTENSIONS = {
    "PNG": {".png"},
    "JPEG": {".jpg", ".jpeg"},
    "GIF": {".gif"},
    "WEBP": {".webp"},
}

NON_IMAGE_MIME_TYPES = {
    ".zip": "application/zip",
    ".pdf": "application/pdf",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json",
}

SAFE_INLINE_MIME_TYPES = frozenset(IMAGE_MIME_TYPES.values())


def _budget(name: str, default: int) -> int:
    return int(getattr(settings, name, default))


def inspect_image(content: bytes) -> dict:
    if not content:
        raise AssetValidationError("图片文件为空。")

    max_dimension = _budget("ASSET_MAX_IMAGE_DIMENSION", 12_000)
    max_pixels = _budget("ASSET_MAX_IMAGE_PIXELS", 40_000_000)
    max_frames = _budget("ASSET_MAX_ANIMATION_FRAMES", 120)
    max_total_pixels = _budget("ASSET_MAX_TOTAL_FRAME_PIXELS", 120_000_000)
    max_duration_ms = _budget("ASSET_MAX_ANIMATION_DURATION_MS", 300_000)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(content)) as image:
                image_format = (image.format or "").upper()
                if image_format not in IMAGE_MIME_TYPES:
                    raise AssetValidationError("只支持 PNG、JPEG、GIF 或 WEBP 图片。")

                frame_count = int(getattr(image, "n_frames", 1) or 1)
                if frame_count > max_frames:
                    raise AssetValidationError(
                        f"图片包含 {frame_count} 帧，超过允许的 {max_frames} 帧。"
                    )

                total_pixels = 0
                duration_ms = 0
                first_width = 0
                first_height = 0
                for frame_index in range(frame_count):
                    image.seek(frame_index)
                    width, height = image.size
                    if frame_index == 0:
                        first_width, first_height = width, height
                    if width <= 0 or height <= 0:
                        raise AssetValidationError("图片尺寸无效。")
                    if width > max_dimension or height > max_dimension:
                        raise AssetValidationError(
                            f"图片尺寸 {width}×{height} 超过单边 {max_dimension}px 限制。"
                        )
                    pixels = width * height
                    if pixels > max_pixels:
                        raise AssetValidationError(
                            f"单帧像素数 {pixels} 超过 {max_pixels} 限制。"
                        )
                    total_pixels += pixels
                    if total_pixels > max_total_pixels:
                        raise AssetValidationError(
                            f"图片累计解码像素数超过 {max_total_pixels} 限制。"
                        )
                    duration_ms += int(image.info.get("duration", 0) or 0)
                    if duration_ms > max_duration_ms:
                        raise AssetValidationError(
                            f"动画总时长超过 {max_duration_ms}ms 限制。"
                        )
                    image.load()

                return {
                    "width": first_width,
                    "height": first_height,
                    "frame_count": frame_count,
                    "duration_ms": duration_ms,
                    "format": image_format,
                    "mode": image.mode,
                    "total_pixels": total_pixels,
                }
    except AssetValidationError:
        raise
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        EOFError,
        OSError,
        ValueError,
    ) as exc:
        raise AssetValidationError("图片无法安全解码，请检查文件是否损坏或超限。") from exc


def _canonical_non_image_mime(filename: str) -> str:
    return NON_IMAGE_MIME_TYPES.get(
        Path(filename).suffix.lower(), "application/octet-stream"
    )


def canonical_mime_for_asset(asset: AssetVersion) -> str:
    if asset.kind in IMAGE_KINDS:
        image_format = str(asset.metadata.get("format", "")).upper()
        return IMAGE_MIME_TYPES.get(image_format, "application/octet-stream")
    return _canonical_non_image_mime(asset.original_name or asset.file.name)


def is_safe_inline_asset(asset: AssetVersion) -> bool:
    return asset.kind in IMAGE_KINDS and canonical_mime_for_asset(asset) in SAFE_INLINE_MIME_TYPES


def create_asset(
    *,
    content: bytes,
    filename: str,
    kind: str,
    source: str,
    actor=None,
    parent: AssetVersion | None = None,
    mime_type: str = "",
    metadata: dict | None = None,
) -> AssetVersion:
    del mime_type  # Client-provided MIME types are intentionally ignored.
    info = inspect_image(content) if kind in IMAGE_KINDS else {}
    original_name = Path(filename).name

    if info:
        suffix = Path(original_name).suffix.lower()
        allowed_suffixes = IMAGE_EXTENSIONS[info["format"]]
        if suffix and suffix not in allowed_suffixes:
            raise AssetValidationError(
                f"文件扩展名 {suffix} 与实际图片格式 {info['format']} 不一致。"
            )
        canonical_mime = IMAGE_MIME_TYPES[info["format"]]
    else:
        canonical_mime = _canonical_non_image_mime(original_name)

    asset = AssetVersion(
        original_name=original_name,
        kind=kind,
        source=source,
        parent=parent,
        mime_type=canonical_mime,
        size_bytes=len(content),
        width=info.get("width", 0),
        height=info.get("height", 0),
        frame_count=info.get("frame_count", 1),
        duration_ms=info.get("duration_ms", 0),
        checksum_sha256=AssetVersion.checksum(content),
        metadata={**(metadata or {}), **info},
        created_by=actor,
    )
    asset.file.save(original_name, ContentFile(content), save=False)
    asset.save()
    return asset


def install_media_hardening() -> None:
    from apps.assets import services

    services.inspect_image = inspect_image
    services.create_asset = create_asset

    # Patch modules that may have imported create_asset before AppConfig.ready().
    for module_name in (
        "apps.emoji.api",
        "apps.emoji.services",
        "apps.emoji.tasks",
        "apps.redpacket.api",
        "apps.redpacket.services",
        "apps.miniprogram.api",
        "apps.miniprogram.services",
    ):
        module = sys.modules.get(module_name)
        if module is not None and hasattr(module, "create_asset"):
            module.create_asset = create_asset
