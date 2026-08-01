import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from django.db import transaction
from PIL import Image, ImageDraw

from apps.assets.models import AssetVersion, PlatformRuleSet
from apps.assets.services import create_asset, read_asset

from .models import (
    RedPacketCampaign,
    RedPacketDesign,
    RedPacketExportBundle,
    RedPacketValidationIssue,
    RedPacketValidationRun,
)
from .pipeline import transition_campaign


def get_ruleset(campaign: RedPacketCampaign) -> PlatformRuleSet:
    if campaign.ruleset_id:
        return campaign.ruleset
    ruleset = (
        PlatformRuleSet.objects.filter(
            platform="wechat",
            product_type="red_packet_cover",
            media_type="static",
            is_active=True,
        )
        .order_by("-effective_at", "-created_at")
        .first()
    )
    if not ruleset:
        raise ValueError("没有可用的微信红包封面规则集。")
    campaign.ruleset = ruleset
    campaign.save(update_fields=["ruleset", "updated_at"])
    return ruleset


def _demo_cover(index: int, size: tuple[int, int]) -> bytes:
    palettes = [
        ((202, 54, 55), (255, 208, 113), (118, 26, 30)),
        ((184, 39, 53), (244, 183, 70), (80, 24, 37)),
        ((224, 73, 61), (255, 226, 154), (126, 36, 43)),
    ]
    background, accent, ink = palettes[index % len(palettes)]
    image = Image.new("RGB", size, background)
    draw = ImageDraw.Draw(image)
    width, height = size
    draw.ellipse(
        (width * 0.12, height * 0.18, width * 0.88, height * 0.76),
        fill=accent,
    )
    draw.ellipse(
        (width * 0.27, height * 0.31, width * 0.73, height * 0.66),
        fill=(250, 242, 224),
    )
    eye_y = int(height * 0.44)
    eye_r = max(8, width // 42)
    for eye_x in (int(width * 0.41), int(width * 0.59)):
        draw.ellipse(
            (eye_x - eye_r, eye_y - eye_r, eye_x + eye_r, eye_y + eye_r),
            fill=ink,
        )
    draw.arc(
        (width * 0.39, height * 0.46, width * 0.61, height * 0.58),
        start=10,
        end=170,
        fill=ink,
        width=max(6, width // 90),
    )
    draw.rounded_rectangle(
        (width * 0.18, height * 0.82, width * 0.82, height * 0.88),
        radius=width * 0.025,
        fill=accent,
    )
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


@transaction.atomic
def generate_demo_designs(campaign: RedPacketCampaign, *, actor=None):
    campaign = RedPacketCampaign.objects.select_for_update().get(pk=campaign.pk)
    if campaign.status == RedPacketCampaign.Status.DRAFT:
        campaign = transition_campaign(
            campaign,
            RedPacketCampaign.Status.BRIEF_APPROVED,
            actor=actor,
            note="确认红包封面 Brief",
        )
    if campaign.status in {
        RedPacketCampaign.Status.BRIEF_APPROVED,
        RedPacketCampaign.Status.REWORK,
    }:
        campaign = transition_campaign(
            campaign,
            RedPacketCampaign.Status.DESIGNING,
            actor=actor,
            note="开始生成封面候选",
        )
    if campaign.status != RedPacketCampaign.Status.DESIGNING:
        raise ValueError("当前状态不能生成新的封面候选。")
    ruleset = get_ruleset(campaign)
    size = tuple(ruleset.constraints.get("cover", {}).get("size", [957, 1278]))
    start_order = (
        campaign.designs.order_by("-order").values_list("order", flat=True).first() or 0
    )
    created = []
    for offset in range(campaign.design_target):
        asset = create_asset(
            content=_demo_cover(offset, size),
            filename=f"red-packet-cover-{start_order + offset + 1:02d}.png",
            kind=AssetVersion.Kind.RED_PACKET_COVER,
            source=AssetVersion.Source.LOCAL,
            actor=actor,
            mime_type="image/png",
            metadata={"generator": "local-red-packet-demo", "variant": offset + 1},
        )
        created.append(
            RedPacketDesign.objects.create(
                campaign=campaign,
                order=start_order + offset + 1,
                title=f"封面方案 {start_order + offset + 1}",
                prompt=(
                    f"{campaign.name}；{campaign.greeting}；"
                    f"{'、'.join(campaign.style_keywords)}"
                ),
                asset=asset,
            )
        )
    transition_campaign(
        campaign,
        RedPacketCampaign.Status.CREATIVE_REVIEW,
        actor=actor,
        note=f"已生成 {len(created)} 个封面候选",
    )
    return created


@transaction.atomic
def select_design(design: RedPacketDesign, *, actor=None):
    campaign = RedPacketCampaign.objects.select_for_update().get(pk=design.campaign_id)
    campaign.designs.filter(is_selected=True).update(is_selected=False, is_approved=False)
    design = RedPacketDesign.objects.get(pk=design.pk)
    design.is_selected = True
    design.save(update_fields=["is_selected", "updated_at"])
    campaign.preview_asset = None
    campaign.save(update_fields=["preview_asset", "updated_at"])
    return design


@transaction.atomic
def approve_selected_design(
    campaign: RedPacketCampaign, *, actor=None, note: str = ""
):
    campaign = RedPacketCampaign.objects.select_for_update().get(pk=campaign.pk)
    design = campaign.designs.filter(is_selected=True).first()
    if not design:
        raise ValueError("请先选择一个封面方案。")
    design.is_approved = True
    design.review_note = note
    design.save(update_fields=["is_approved", "review_note", "updated_at"])
    if campaign.status in {
        RedPacketCampaign.Status.CREATIVE_REVIEW,
        RedPacketCampaign.Status.REWORK,
    }:
        transition_campaign(
            campaign,
            RedPacketCampaign.Status.RIGHTS_REVIEW,
            actor=actor,
            note=note or "封面方案已完成创意确认",
        )
    return design


def ensure_preview(campaign: RedPacketCampaign, *, actor=None):
    selected = campaign.selected_design
    if not selected:
        return None
    if campaign.preview_asset_id:
        return campaign.preview_asset
    with Image.open(io.BytesIO(read_asset(selected.asset))) as source:
        image = source.convert("RGB")
        image.thumbnail((360, 360), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (750, 400), (248, 246, 246))
        canvas.paste(image, ((750 - image.width) // 2, (400 - image.height) // 2))
        output = io.BytesIO()
        canvas.save(output, format="PNG", optimize=True)
    preview = create_asset(
        content=output.getvalue(),
        filename="red-packet-preview.png",
        kind=AssetVersion.Kind.RED_PACKET_PREVIEW,
        source=AssetVersion.Source.PROCESSOR,
        actor=actor,
        parent=selected.asset,
        mime_type="image/png",
        metadata={"processor": "red-packet-preview", "target_size": [750, 400]},
    )
    campaign.preview_asset = preview
    campaign.save(update_fields=["preview_asset", "updated_at"])
    return preview


def _issue(run, *, code, message, remediation, severity="error"):
    return RedPacketValidationIssue.objects.create(
        run=run,
        code=code,
        severity=severity,
        message=message,
        remediation=remediation,
    )


@transaction.atomic
def validate_campaign(
    campaign: RedPacketCampaign, *, actor=None
) -> RedPacketValidationRun:
    campaign = RedPacketCampaign.objects.select_related("project", "ruleset").get(
        pk=campaign.pk
    )
    if campaign.status in {
        RedPacketCampaign.Status.RIGHTS_REVIEW,
        RedPacketCampaign.Status.REWORK,
    }:
        campaign = transition_campaign(
            campaign,
            RedPacketCampaign.Status.QA_REVIEW,
            actor=actor,
            note="开始红包封面确定性 QA",
        )
    ruleset = get_ruleset(campaign)
    constraints = ruleset.constraints
    run = RedPacketValidationRun.objects.create(
        campaign=campaign, ruleset=ruleset, created_by=actor
    )
    selected = campaign.selected_design
    if not selected:
        _issue(
            run,
            code="design.missing",
            message="尚未选择最终封面方案。",
            remediation="从候选中选择一个封面并完成创意确认。",
        )
    else:
        if not selected.is_approved:
            _issue(
                run,
                code="design.not_approved",
                message="最终封面尚未通过创意确认。",
                remediation="由审核人员确认最终方案。",
            )
        cover_rule = constraints.get("cover", {})
        expected_size = cover_rule.get("size", [957, 1278])
        if [selected.asset.width, selected.asset.height] != expected_size:
            _issue(
                run,
                code="cover.dimensions",
                message=(
                    f"封面尺寸为 {selected.asset.width}×{selected.asset.height}，"
                    f"当前规则要求 {expected_size[0]}×{expected_size[1]}。"
                ),
                remediation="重新规范化封面尺寸。",
            )
        if selected.asset.size_bytes > int(
            cover_rule.get("max_bytes", 2 * 1024 * 1024)
        ):
            _issue(
                run,
                code="cover.file_size",
                message="封面文件超过当前规则的体积上限。",
                remediation="压缩封面后重新上传。",
            )
        suffix = Path(selected.asset.original_name).suffix.lower()
        allowed_formats = [
            f".{item.lower()}" for item in cover_rule.get("formats", ["PNG", "JPG"])
        ]
        if suffix not in allowed_formats:
            _issue(
                run,
                code="cover.format",
                message=f"封面格式 {suffix or '未知'} 不符合当前规则。",
                remediation=f"转换为 {'/'.join(allowed_formats)}。",
            )
    if constraints.get("story_required", True) and not campaign.cover_story.strip():
        _issue(
            run,
            code="story.missing",
            message="封面故事不能为空。",
            remediation="补充用户可理解的封面故事。",
        )
    rights_count = campaign.project.rights_evidence.count()
    if not rights_count:
        _issue(
            run,
            code="rights.missing",
            message="项目尚未登记权利材料。",
            remediation="正式提交前上传原创声明或授权证明。",
            severity=(
                "error" if constraints.get("rights_required", False) else "warning"
            ),
        )
    errors = run.issues.filter(
        severity=RedPacketValidationIssue.Severity.ERROR
    ).count()
    warnings = run.issues.filter(
        severity=RedPacketValidationIssue.Severity.WARNING
    ).count()
    run.passed = errors == 0
    run.error_count = errors
    run.warning_count = warnings
    run.summary = {
        "design_count": campaign.designs.count(),
        "selected_design_id": str(selected.pk) if selected else None,
        "rights_evidence_count": rights_count,
    }
    run.save(
        update_fields=[
            "passed",
            "error_count",
            "warning_count",
            "summary",
            "updated_at",
        ]
    )
    return run


@transaction.atomic
def build_export_bundle(
    campaign: RedPacketCampaign, *, actor=None
) -> RedPacketExportBundle:
    run = validate_campaign(campaign, actor=actor)
    if not run.passed:
        raise ValueError(f"QA 未通过：仍有 {run.error_count} 个错误。")
    campaign.refresh_from_db()
    selected = campaign.selected_design
    preview = ensure_preview(campaign, actor=actor)
    rights = list(campaign.project.rights_evidence.all())
    manifest = {
        "schema": "wx-product.red-packet-cover.export.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "campaign": {
            "id": str(campaign.pk),
            "name": campaign.name,
            "greeting": campaign.greeting,
            "cover_story": campaign.cover_story,
            "planned_quantity": campaign.planned_quantity,
        },
        "ruleset": {
            "id": str(run.ruleset_id),
            "version": run.ruleset.version,
            "constraints": run.ruleset.constraints,
        },
        "cover": {
            "filename": "cover/cover.png",
            "asset_id": str(selected.asset_id),
            "checksum_sha256": selected.asset.checksum_sha256,
        },
        "preview": "support/preview.png",
        "rights_evidence_count": len(rights),
    }
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
        )
        archive.writestr(
            "README.txt",
            "该文件由微信造物台生成。提交前请由运营人员复核当期微信红包封面规则。",
        )
        archive.writestr("cover/cover.png", read_asset(selected.asset))
        archive.writestr("support/preview.png", read_asset(preview))
        for index, evidence in enumerate(rights, start=1):
            if evidence.proof_file:
                suffix = Path(evidence.proof_file.name).suffix
                with evidence.proof_file.open("rb") as source:
                    archive.writestr(f"rights/{index:02d}{suffix}", source.read())
        if not rights:
            archive.writestr("rights/README.txt", "正式提交前补充原创声明或授权材料。")
    content = output.getvalue()
    file_asset = create_asset(
        content=content,
        filename=f"red-packet-{campaign.pk}.zip",
        kind=AssetVersion.Kind.EXPORT,
        source=AssetVersion.Source.EXPORTER,
        actor=actor,
        mime_type="application/zip",
        metadata={"export_schema": manifest["schema"]},
    )
    bundle = RedPacketExportBundle.objects.create(
        campaign=campaign,
        ruleset=run.ruleset,
        file=file_asset,
        manifest=manifest,
        checksum_sha256=file_asset.checksum_sha256,
        created_by=actor,
    )
    if campaign.status == RedPacketCampaign.Status.QA_REVIEW:
        transition_campaign(
            campaign,
            RedPacketCampaign.Status.EXPORT_READY,
            actor=actor,
            note="红包封面 QA 通过并冻结导出规则",
        )
    return bundle
