import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from PIL import Image

from apps.assets.models import AssetVersion, PlatformRuleSet
from apps.assets.services import create_asset, read_asset
from apps.core.models import TransitionEvent

from .models import (
    EmojiPack,
    ExportBundle,
    ValidationIssue,
    ValidationRun,
)


def get_ruleset(pack: EmojiPack) -> PlatformRuleSet:
    if pack.ruleset_id:
        return pack.ruleset
    ruleset = (
        PlatformRuleSet.objects.filter(
            platform="wechat",
            product_type="emoji",
            media_type=pack.media_type,
            is_active=True,
        )
        .order_by("-effective_at", "-created_at")
        .first()
    )
    if not ruleset:
        raise ValueError(f"没有可用的微信表情 {pack.get_media_type_display()} 规则集。")
    pack.ruleset = ruleset
    pack.save(update_fields=["ruleset", "updated_at"])
    return ruleset


def ensure_support_assets(pack: EmojiPack, *, actor=None):
    first_asset = (
        pack.items.exclude(selected_asset=None)
        .select_related("selected_asset")
        .order_by("order")
        .values_list("selected_asset", flat=True)
        .first()
    )
    if not first_asset:
        return
    source_asset = AssetVersion.objects.get(pk=first_asset)
    source = Image.open(io.BytesIO(read_asset(source_asset))).convert("RGBA")
    updates = {}
    if not pack.cover_asset_id:
        updates["cover_asset"] = _make_support_image(
            source,
            size=(240, 240),
            kind=AssetVersion.Kind.COVER,
            filename="cover.png",
            actor=actor,
            parent=source_asset,
        )
    if not pack.icon_asset_id:
        updates["icon_asset"] = _make_support_image(
            source,
            size=(50, 50),
            kind=AssetVersion.Kind.ICON,
            filename="icon.png",
            actor=actor,
            parent=source_asset,
        )
    if not pack.banner_asset_id:
        canvas = Image.new("RGBA", (750, 400), (248, 245, 246, 255))
        preview = source.copy()
        preview.thumbnail((360, 360), Image.Resampling.LANCZOS)
        canvas.alpha_composite(preview, ((750 - preview.width) // 2, 20))
        out = io.BytesIO()
        canvas.save(out, format="PNG", optimize=True)
        updates["banner_asset"] = create_asset(
            content=out.getvalue(),
            filename="banner.png",
            kind=AssetVersion.Kind.BANNER,
            source=AssetVersion.Source.PROCESSOR,
            actor=actor,
            parent=source_asset,
            mime_type="image/png",
            metadata={"processor": "support-banner", "target_size": [750, 400]},
        )
    if updates:
        for field, value in updates.items():
            setattr(pack, field, value)
        pack.save(update_fields=[*updates.keys(), "updated_at"])


def _make_support_image(source, *, size, kind, filename, actor, parent):
    image = source.copy()
    image.thumbnail(size, Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.alpha_composite(
        image, ((size[0] - image.width) // 2, (size[1] - image.height) // 2)
    )
    out = io.BytesIO()
    canvas.save(out, format="PNG", optimize=True)
    return create_asset(
        content=out.getvalue(),
        filename=filename,
        kind=kind,
        source=AssetVersion.Source.PROCESSOR,
        actor=actor,
        parent=parent,
        mime_type="image/png",
        metadata={"processor": "support-resize", "target_size": list(size)},
    )


@transaction.atomic
def validate_pack(pack: EmojiPack, *, actor=None) -> ValidationRun:
    pack = EmojiPack.objects.select_related("project", "ruleset").get(pk=pack.pk)
    ensure_support_assets(pack, actor=actor)
    ruleset = get_ruleset(pack)
    constraints = ruleset.constraints
    run = ValidationRun.objects.create(pack=pack, ruleset=ruleset, created_by=actor)
    items = list(pack.items.select_related("selected_asset").order_by("order"))

    if pack.pack_type == EmojiPack.PackType.SINGLE:
        allowed_counts = [1]
    else:
        allowed_counts = constraints.get("allowed_counts", [8, 16, 24])
    if pack.target_count not in allowed_counts:
        _issue(
            run,
            code="pack.target_count",
            message=f"目标数量 {pack.target_count} 不在规则允许的 {allowed_counts} 中。",
            remediation="调整目标数量或在后台更新规则版本。",
        )
    if len(items) != pack.target_count:
        _issue(
            run,
            code="pack.item_count",
            message=f"当前有 {len(items)} 个语义项，目标为 {pack.target_count}。",
            remediation="重新生成语义矩阵或补齐缺失项。",
        )

    trend = pack.project.trend_topic
    if trend and trend.expires_at <= timezone.now():
        _issue(
            run,
            code="project.trend_expired",
            message="关联热点已经过期，不能继续导出投稿包。",
            remediation="关闭项目或更新经过审核的新热点来源。",
        )

    item_rule = constraints.get("item", {})
    expected_format = item_rule.get(
        "format", "PNG" if pack.media_type == EmojiPack.MediaType.STATIC else "GIF"
    ).upper()
    expected_size = item_rule.get("size", [240, 240])
    max_bytes = int(item_rule.get("max_bytes", 500 * 1024))
    for item in items:
        asset = item.selected_asset
        if not asset:
            _issue(
                run,
                item=item,
                code="item.asset_missing",
                message=f"第 {item.order} 项“{item.meaning}”尚未选择成品。",
                remediation="生成或上传候选后选择最终素材。",
            )
            continue
        suffix = Path(asset.original_name).suffix.lstrip(".").upper()
        if suffix != expected_format:
            _issue(
                run,
                item=item,
                asset=asset,
                code="asset.format",
                message=f"成品格式为 {suffix or '未知'}，规则要求 {expected_format}。",
                remediation="重新执行媒体处理。",
            )
        if [asset.width, asset.height] != expected_size:
            _issue(
                run,
                item=item,
                asset=asset,
                code="asset.dimensions",
                message=(
                    f"成品尺寸为 {asset.width}×{asset.height}，"
                    f"规则要求 {expected_size[0]}×{expected_size[1]}。"
                ),
                remediation="重新规范化尺寸。",
            )
        if asset.size_bytes > max_bytes:
            _issue(
                run,
                item=item,
                asset=asset,
                code="asset.file_size",
                message=f"成品大小 {asset.size_bytes}B 超过 {max_bytes}B。",
                remediation="降低 GIF 色数/帧数或压缩 PNG。",
            )
        if pack.media_type == EmojiPack.MediaType.DYNAMIC and asset.frame_count < 2:
            _issue(
                run,
                item=item,
                asset=asset,
                code="asset.not_animated",
                message="动态表情必须包含至少 2 帧。",
                remediation="在序列帧编辑器中补充帧并重新合成。",
            )
        if not item.is_approved:
            _issue(
                run,
                item=item,
                asset=asset,
                code="item.not_approved",
                severity=ValidationIssue.Severity.WARNING,
                message=f"第 {item.order} 项尚未人工确认。",
                remediation="由 reviewer 完成创意确认。",
            )

    support_rules = constraints.get(
        "support",
        {
            "cover": [240, 240],
            "icon": [50, 50],
            "banner": [750, 400],
        },
    )
    for field_name, expected in support_rules.items():
        asset = getattr(pack, f"{field_name}_asset", None)
        if not asset:
            _issue(
                run,
                code=f"support.{field_name}_missing",
                message=f"缺少{field_name}素材。",
                remediation="重新生成辅助素材。",
            )
        elif [asset.width, asset.height] != expected:
            _issue(
                run,
                asset=asset,
                code=f"support.{field_name}_dimensions",
                message=f"{field_name} 尺寸不符合 {expected[0]}×{expected[1]}。",
                remediation="重新生成辅助素材。",
            )

    if not pack.project.rights_evidence.exists():
        _issue(
            run,
            code="rights.evidence_missing",
            severity=ValidationIssue.Severity.WARNING,
            message="项目尚未登记原创声明或授权证明。",
            remediation="在项目后台补充权利材料，并由 reviewer 人工确认。",
        )

    error_count = run.issues.filter(severity=ValidationIssue.Severity.ERROR).count()
    warning_count = run.issues.filter(severity=ValidationIssue.Severity.WARNING).count()
    run.error_count = error_count
    run.warning_count = warning_count
    run.passed = error_count == 0
    run.summary = {
        "items": len(items),
        "selected": sum(1 for item in items if item.selected_asset_id),
        "ruleset": str(ruleset),
    }
    run.save(
        update_fields=["error_count", "warning_count", "passed", "summary", "updated_at"]
    )
    if pack.status in {
        EmojiPack.Status.PROCESSING,
        EmojiPack.Status.CREATIVE_REVIEW,
        EmojiPack.Status.REWORK,
    }:
        old_status = pack.status
        pack.status = EmojiPack.Status.QA_REVIEW
        pack.save(update_fields=["status", "updated_at"])
        TransitionEvent.objects.create(
            object_type="emoji_pack",
            object_id=pack.pk,
            from_state=old_status,
            to_state=pack.status,
            action="validation",
            actor=actor,
            payload={"run_id": str(run.pk), "passed": run.passed},
        )
    return run


def _issue(
    run,
    *,
    code,
    message,
    remediation,
    severity=ValidationIssue.Severity.ERROR,
    item=None,
    asset=None,
):
    return ValidationIssue.objects.create(
        run=run,
        item=item,
        asset=asset,
        code=code,
        severity=severity,
        message=message,
        remediation=remediation,
    )


@transaction.atomic
def build_export_bundle(pack: EmojiPack, *, actor=None) -> ExportBundle:
    pack = EmojiPack.objects.select_for_update().select_related("project").get(pk=pack.pk)
    run = validate_pack(pack, actor=actor)
    if not run.passed:
        raise ValueError(f"QA 存在 {run.error_count} 个错误，不能导出。")
    pack.refresh_from_db()
    ruleset = run.ruleset
    items = list(pack.items.select_related("selected_asset").order_by("order"))
    suffix = "png" if pack.media_type == EmojiPack.MediaType.STATIC else "gif"
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "pack": {
            "id": str(pack.pk),
            "name": pack.name,
            "description": pack.description,
            "type": pack.pack_type,
            "media_type": pack.media_type,
            "project": pack.project.title,
        },
        "ruleset": {
            "id": str(ruleset.pk),
            "version": ruleset.version,
            "effective_at": ruleset.effective_at.isoformat(),
            "constraints": ruleset.constraints,
        },
        "items": [
            {
                "order": item.order,
                "meaning": item.meaning,
                "copy_text": item.copy_text,
                "filename": f"emoji/{item.order:02d}.{suffix}",
                "asset_id": str(item.selected_asset_id),
                "checksum_sha256": item.selected_asset.checksum_sha256,
            }
            for item in items
        ],
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
        for item in items:
            bundle.writestr(
                f"emoji/{item.order:02d}.{suffix}",
                read_asset(item.selected_asset),
            )
        for field, filename in (
            ("cover_asset", "support/cover.png"),
            ("icon_asset", "support/icon.png"),
            ("banner_asset", "support/banner.png"),
        ):
            bundle.writestr(filename, read_asset(getattr(pack, field)))
        bundle.writestr(
            "manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
        )
        bundle.writestr(
            "submission-checklist.txt",
            (
                "微信表情人工投稿清单\n"
                "1. 在微信表情开放平台确认当前素材规格。\n"
                "2. 按 manifest.json 顺序上传主图。\n"
                "3. 上传 support 目录中的图标、封面和横幅。\n"
                "4. 补充权利证明并完成平台合规检查。\n"
                "5. 提交后在造物台登记作品编号与审核结果。\n"
            ).encode(),
        )
        for evidence in pack.project.rights_evidence.exclude(proof_file=""):
            with evidence.proof_file.open("rb") as proof:
                bundle.writestr(
                    f"rights/{evidence.kind}-{Path(evidence.proof_file.name).name}",
                    proof.read(),
                )
    content = output.getvalue()
    asset = create_asset(
        content=content,
        filename=f"{pack.name}-{ruleset.version}.zip",
        kind=AssetVersion.Kind.EXPORT,
        source=AssetVersion.Source.EXPORTER,
        actor=actor,
        mime_type="application/zip",
        metadata={"pack_id": str(pack.pk), "ruleset_id": str(ruleset.pk)},
    )
    export = ExportBundle.objects.create(
        pack=pack,
        ruleset=ruleset,
        file=asset,
        manifest=manifest,
        checksum_sha256=asset.checksum_sha256,
        created_by=actor,
    )
    if pack.status == EmojiPack.Status.QA_REVIEW:
        old = pack.status
        pack.status = EmojiPack.Status.EXPORT_READY
        pack.save(update_fields=["status", "updated_at"])
        TransitionEvent.objects.create(
            object_type="emoji_pack",
            object_id=pack.pk,
            from_state=old,
            to_state=pack.status,
            action="export",
            actor=actor,
            payload={"export_id": str(export.pk)},
        )
    return export
