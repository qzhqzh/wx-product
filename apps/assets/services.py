import io
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

from .models import AssetVersion


def inspect_image(content: bytes) -> dict:
    with Image.open(io.BytesIO(content)) as image:
        frame_count = getattr(image, "n_frames", 1)
        duration_ms = 0
        for frame_index in range(frame_count):
            image.seek(frame_index)
            duration_ms += int(image.info.get("duration", 0))
        return {
            "width": image.width,
            "height": image.height,
            "frame_count": frame_count,
            "duration_ms": duration_ms,
            "format": image.format,
            "mode": image.mode,
        }


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
    image_kinds = {
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
    info = inspect_image(content) if kind in image_kinds else {}
    asset = AssetVersion(
        original_name=Path(filename).name,
        kind=kind,
        source=source,
        parent=parent,
        mime_type=mime_type,
        size_bytes=len(content),
        width=info.get("width", 0),
        height=info.get("height", 0),
        frame_count=info.get("frame_count", 1),
        duration_ms=info.get("duration_ms", 0),
        checksum_sha256=AssetVersion.checksum(content),
        metadata={**(metadata or {}), **info},
        created_by=actor,
    )
    asset.file.save(filename, ContentFile(content), save=False)
    asset.save()
    return asset


def read_asset(asset: AssetVersion) -> bytes:
    with asset.file.open("rb") as source:
        return source.read()


def normalize_static_asset(
    asset: AssetVersion,
    *,
    actor=None,
    size: tuple[int, int] = (240, 240),
    kind: str = AssetVersion.Kind.FINAL_STATIC,
) -> AssetVersion:
    with Image.open(io.BytesIO(read_asset(asset))) as source:
        image = source.convert("RGBA")
        image.thumbnail(size, Image.Resampling.LANCZOS)
        canvas = Image.new("RGBA", size, (0, 0, 0, 0))
        offset = ((size[0] - image.width) // 2, (size[1] - image.height) // 2)
        canvas.alpha_composite(image, offset)
        out = io.BytesIO()
        canvas.save(out, format="PNG", optimize=True)
    return create_asset(
        content=out.getvalue(),
        filename=f"{Path(asset.original_name).stem}-240.png",
        kind=kind,
        source=AssetVersion.Source.PROCESSOR,
        actor=actor,
        parent=asset,
        mime_type="image/png",
        metadata={"processor": "normalize-static", "target_size": list(size)},
    )


def transform_frame(
    base_asset: AssetVersion, *, frame_index: int, total_frames: int, actor=None
) -> AssetVersion:
    with Image.open(io.BytesIO(read_asset(base_asset))) as source:
        base = source.convert("RGBA")
        phase = frame_index / max(total_frames, 1) * 6.283185
        import math

        scale = 0.94 + 0.05 * (1 + math.sin(phase))
        angle = 2.5 * math.sin(phase)
        resized = base.resize(
            (max(1, int(base.width * scale)), max(1, int(base.height * scale))),
            Image.Resampling.LANCZOS,
        ).rotate(angle, resample=Image.Resampling.BICUBIC, expand=True)
        canvas = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
        x = (240 - resized.width) // 2 + int(5 * math.cos(phase))
        y = (240 - resized.height) // 2 + int(5 * math.sin(phase))
        canvas.alpha_composite(resized, (x, y))
        out = io.BytesIO()
        canvas.save(out, format="PNG", optimize=True)
    return create_asset(
        content=out.getvalue(),
        filename=f"frame-{frame_index + 1:02d}.png",
        kind=AssetVersion.Kind.ANIMATION_FRAME,
        source=AssetVersion.Source.PROCESSOR,
        actor=actor,
        parent=base_asset,
        mime_type="image/png",
        metadata={"processor": "sequence-transform", "frame_index": frame_index},
    )


def assemble_gif(sequence, *, actor=None) -> AssetVersion:
    frames = list(sequence.frames.select_related("asset").order_by("order"))
    if len(frames) < 2:
        raise ValueError("动态表情至少需要 2 帧。")
    images = []
    durations = []
    for frame in frames:
        with Image.open(io.BytesIO(read_asset(frame.asset))) as source:
            normalized = ImageOps.contain(source.convert("RGBA"), (240, 240))
            canvas = Image.new("RGBA", (240, 240), (0, 0, 0, 0))
            canvas.alpha_composite(
                normalized,
                ((240 - normalized.width) // 2, (240 - normalized.height) // 2),
            )
            images.append(canvas)
            durations.append(frame.duration_ms)
    content = _encode_gif(images, durations, sequence.loop_count)
    asset = create_asset(
        content=content,
        filename=f"{sequence.item.order:02d}-{sequence.item.meaning}.gif",
        kind=AssetVersion.Kind.FINAL_GIF,
        source=AssetVersion.Source.PROCESSOR,
        actor=actor,
        mime_type="image/gif",
        metadata={"processor": "pillow-gif", "loop_count": sequence.loop_count},
    )
    sequence.output_asset = asset
    sequence.status = "ready"
    sequence.save(update_fields=["output_asset", "status", "updated_at"])
    sequence.item.candidates.add(asset)
    sequence.item.selected_asset = asset
    sequence.item.save(update_fields=["selected_asset", "updated_at"])
    return asset


def _encode_gif(images, durations, loop_count):
    for colors in (128, 96, 64, 48, 32):
        converted = [
            frame.convert("P", palette=Image.Palette.ADAPTIVE, colors=colors)
            for frame in images
        ]
        out = io.BytesIO()
        converted[0].save(
            out,
            format="GIF",
            save_all=True,
            append_images=converted[1:],
            duration=durations,
            loop=loop_count,
            disposal=2,
            transparency=0,
            optimize=False,
        )
        if len(out.getvalue()) <= 500 * 1024 or colors == 32:
            return out.getvalue()
    raise RuntimeError("GIF 编码失败。")
