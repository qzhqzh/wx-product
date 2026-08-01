import io
import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.assets.models import AssetVersion, PlatformRuleSet
from apps.assets.services import create_asset, read_asset

from .models import (
    MiniProgramArtifact,
    MiniProgramChecklistItem,
    MiniProgramExportBundle,
    MiniProgramRelease,
    MiniProgramTestCase,
    MiniProgramValidationIssue,
    MiniProgramValidationRun,
)
from .pipeline import transition_release

DEFAULT_CHECKLIST = [
    ("prd", "本次版本范围、非目标和验收标准已确认"),
    ("build", "生产构建配置与版本号一致"),
    ("functional", "核心业务路径已完成体验版验收"),
    ("privacy", "隐私政策、用户信息处理和授权时机已复核"),
    ("security", "敏感信息、接口权限和错误输出已检查"),
    ("platform", "类目、版本说明、截图和审核备注已准备"),
]

DEFAULT_TEST_CASES = [
    (
        "首次进入与授权边界",
        ["清理小程序缓存", "首次进入首页", "触发需要授权的功能"],
        "进入页面不强制授权；需要权限时说明用途并由用户主动确认。",
    ),
    (
        "核心业务闭环",
        ["进入主要功能", "填写有效数据", "提交并查看结果"],
        "提交成功，结果可见，重复提交有明确反馈。",
    ),
    (
        "弱网与接口失败",
        ["模拟接口失败", "执行主要操作", "恢复网络后重试"],
        "失败信息可理解，不丢失已填写数据，恢复后可以重试。",
    ),
]


def get_ruleset(release: MiniProgramRelease) -> PlatformRuleSet:
    if release.ruleset_id:
        return release.ruleset
    ruleset = (
        PlatformRuleSet.objects.filter(
            platform="wechat",
            product_type="mini_program",
            media_type="release",
            is_active=True,
        )
        .order_by("-effective_at", "-created_at")
        .first()
    )
    if not ruleset:
        raise ValueError("没有可用的微信小程序发布规则集。")
    release.ruleset = ruleset
    release.save(update_fields=["ruleset", "updated_at"])
    return ruleset


def ensure_default_checklist(release: MiniProgramRelease):
    items = []
    for category, title in DEFAULT_CHECKLIST:
        item, _ = MiniProgramChecklistItem.objects.get_or_create(
            release=release,
            category=category,
            title=title,
            defaults={"is_required": True},
        )
        items.append(item)
    return items


def ensure_default_tests(release: MiniProgramRelease):
    cases = []
    for name, steps, expected in DEFAULT_TEST_CASES:
        case, _ = MiniProgramTestCase.objects.get_or_create(
            release=release,
            name=name,
            defaults={"steps": steps, "expected_result": expected},
        )
        cases.append(case)
    return cases


def _demo_build_package(release: MiniProgramRelease) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "app.json",
            json.dumps(
                {
                    "pages": ["pages/index/index"],
                    "window": {"navigationBarTitleText": release.name},
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        archive.writestr(
            "pages/index/index.js",
            "Page({ data: { status: 'demo-ready' } });\n",
        )
        archive.writestr(
            "BUILD_INFO.json",
            json.dumps(
                {"version": release.version, "generated_by": "wx-product-local-demo"},
                ensure_ascii=False,
                indent=2,
            ),
        )
    return output.getvalue()


def _demo_qr(size=(480, 480)) -> bytes:
    image = Image.new("RGB", size, (255, 255, 255))
    draw = ImageDraw.Draw(image)
    cell = size[0] // 24
    for row in range(2, 22):
        for column in range(2, 22):
            if (row * 7 + column * 11 + row * column) % 5 in {0, 1}:
                draw.rectangle(
                    (
                        column * cell,
                        row * cell,
                        (column + 1) * cell - 1,
                        (row + 1) * cell - 1,
                    ),
                    fill=(32, 44, 54),
                )
    for x, y in ((2, 2), (16, 2), (2, 16)):
        draw.rectangle(
            (x * cell, y * cell, (x + 5) * cell, (y + 5) * cell),
            outline=(213, 60, 64),
            width=max(5, cell // 3),
        )
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def _demo_screenshot(index: int, size=(750, 1334)) -> bytes:
    image = Image.new("RGB", size, (248, 249, 250))
    draw = ImageDraw.Draw(image)
    width, height = size
    draw.rectangle((0, 0, width, 150), fill=(210, 55, 62))
    draw.rounded_rectangle(
        (50, 210, width - 50, 430),
        radius=18,
        fill=(255, 255, 255),
        outline=(220, 224, 228),
        width=2,
    )
    for row in range(4):
        top = 500 + row * 150
        draw.rounded_rectangle(
            (50, top, width - 50, top + 110),
            radius=12,
            fill=(255, 255, 255),
            outline=(224, 227, 230),
            width=2,
        )
        draw.ellipse((75, top + 24, 135, top + 84), fill=(230, 82 + index * 12, 85))
        draw.rectangle((165, top + 30, width - 90, top + 46), fill=(68, 78, 88))
        draw.rectangle((165, top + 64, width - 190, top + 76), fill=(170, 177, 184))
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()


def create_artifact(
    release: MiniProgramRelease,
    *,
    artifact_type: str,
    label: str,
    content: bytes,
    filename: str,
    kind: str,
    mime_type: str,
    actor=None,
    notes: str = "",
    source=AssetVersion.Source.LOCAL,
):
    if artifact_type in {
        MiniProgramArtifact.ArtifactType.BUILD_PACKAGE,
        MiniProgramArtifact.ArtifactType.EXPERIENCE_QR,
        MiniProgramArtifact.ArtifactType.PRIVACY_DOCUMENT,
    }:
        release.artifacts.filter(
            artifact_type=artifact_type, is_current=True
        ).update(is_current=False)
    asset = create_asset(
        content=content,
        filename=filename,
        kind=kind,
        source=source,
        actor=actor,
        mime_type=mime_type,
        metadata={"mini_program_artifact_type": artifact_type},
    )
    return MiniProgramArtifact.objects.create(
        release=release,
        artifact_type=artifact_type,
        label=label,
        asset=asset,
        notes=notes,
    )


@transaction.atomic
def generate_demo_release(release: MiniProgramRelease, *, actor=None):
    release = MiniProgramRelease.objects.select_for_update().get(pk=release.pk)
    if release.status == MiniProgramRelease.Status.DRAFT:
        release = transition_release(
            release,
            MiniProgramRelease.Status.PRD_APPROVED,
            actor=actor,
            note="确认 PRD、版本范围和验收标准",
        )
    if release.status in {
        MiniProgramRelease.Status.PRD_APPROVED,
        MiniProgramRelease.Status.REWORK,
    }:
        release = transition_release(
            release,
            MiniProgramRelease.Status.DEVELOPING,
            actor=actor,
            note="进入开发与构建",
        )
    if release.status != MiniProgramRelease.Status.DEVELOPING:
        raise ValueError("当前状态不能生成演示构建。")
    ensure_default_checklist(release)
    ensure_default_tests(release)
    create_artifact(
        release,
        artifact_type=MiniProgramArtifact.ArtifactType.BUILD_PACKAGE,
        label=f"{release.version} 演示构建包",
        content=_demo_build_package(release),
        filename=f"mini-program-{release.version}.zip",
        kind=AssetVersion.Kind.BUILD_PACKAGE,
        mime_type="application/zip",
        actor=actor,
    )
    create_artifact(
        release,
        artifact_type=MiniProgramArtifact.ArtifactType.EXPERIENCE_QR,
        label="体验版二维码",
        content=_demo_qr(),
        filename="experience-qr.png",
        kind=AssetVersion.Kind.EXPERIENCE_QR,
        mime_type="image/png",
        actor=actor,
    )
    for index in range(2):
        create_artifact(
            release,
            artifact_type=MiniProgramArtifact.ArtifactType.SCREENSHOT,
            label=f"审核截图 {index + 1}",
            content=_demo_screenshot(index),
            filename=f"screenshot-{index + 1}.png",
            kind=AssetVersion.Kind.SCREENSHOT,
            mime_type="image/png",
            actor=actor,
        )
    release.checklist_items.update(is_completed=True, note="本地案例已完成检查")
    release.test_cases.update(
        result=MiniProgramTestCase.Result.PASSED,
        actual_result="本地案例执行结果符合预期。",
        executed_by=actor,
        executed_at=timezone.now(),
    )
    release = transition_release(
        release,
        MiniProgramRelease.Status.BUILD_READY,
        actor=actor,
        note="演示构建包已生成",
    )
    release = transition_release(
        release,
        MiniProgramRelease.Status.EXPERIENCE_REVIEW,
        actor=actor,
        note="体验版功能用例全部通过",
    )
    transition_release(
        release,
        MiniProgramRelease.Status.COMPLIANCE_REVIEW,
        actor=actor,
        note="进入隐私与微信平台资料复核",
    )
    return release


def _issue(run, *, code, message, remediation, severity="error"):
    return MiniProgramValidationIssue.objects.create(
        run=run,
        code=code,
        severity=severity,
        message=message,
        remediation=remediation,
    )


@transaction.atomic
def validate_release(
    release: MiniProgramRelease, *, actor=None
) -> MiniProgramValidationRun:
    release = MiniProgramRelease.objects.select_related("ruleset").get(pk=release.pk)
    if release.status in {
        MiniProgramRelease.Status.COMPLIANCE_REVIEW,
        MiniProgramRelease.Status.REWORK,
    }:
        release = transition_release(
            release,
            MiniProgramRelease.Status.QA_REVIEW,
            actor=actor,
            note="开始小程序发布 QA",
        )
    ruleset = get_ruleset(release)
    constraints = ruleset.constraints
    run = MiniProgramValidationRun.objects.create(
        release=release, ruleset=ruleset, created_by=actor
    )
    if not release.prd_summary.strip():
        _issue(
            run,
            code="prd.missing",
            message="PRD 摘要为空。",
            remediation="补充版本范围、非目标和验收标准。",
        )
    if constraints.get("privacy_summary_required", True) and not release.privacy_summary.strip():
        _issue(
            run,
            code="privacy.summary_missing",
            message="隐私处理摘要为空。",
            remediation="说明使用的用户信息、用途、授权时机和删除方式。",
        )
    if not release.app_id.strip():
        _issue(
            run,
            code="platform.app_id_missing",
            message="尚未登记小程序 AppID。",
            remediation="正式提交前补充实际 AppID。",
            severity="warning",
        )
    required_artifacts = constraints.get(
        "required_artifacts", ["build_package", "experience_qr", "screenshot"]
    )
    current_artifacts = release.artifacts.filter(is_current=True)
    for artifact_type in required_artifacts:
        if not current_artifacts.filter(artifact_type=artifact_type).exists():
            _issue(
                run,
                code=f"artifact.{artifact_type}_missing",
                message=f"缺少必需产物：{artifact_type}。",
                remediation="上传当前版本产物后重新检查。",
            )
    screenshots = current_artifacts.filter(
        artifact_type=MiniProgramArtifact.ArtifactType.SCREENSHOT
    ).count()
    minimum_screenshots = int(constraints.get("min_screenshots", 2))
    if screenshots < minimum_screenshots:
        _issue(
            run,
            code="artifact.screenshot_count",
            message=f"当前有 {screenshots} 张审核截图，至少需要 {minimum_screenshots} 张。",
            remediation="补充能覆盖核心功能的审核截图。",
        )
    build = current_artifacts.filter(
        artifact_type=MiniProgramArtifact.ArtifactType.BUILD_PACKAGE
    ).first()
    if build:
        build_rule = constraints.get("build", {})
        suffix = Path(build.asset.original_name).suffix.lower()
        allowed = [f".{item.lower()}" for item in build_rule.get("formats", ["ZIP"])]
        if suffix not in allowed:
            _issue(
                run,
                code="build.format",
                message=f"构建包格式 {suffix or '未知'} 不符合当前规则。",
                remediation=f"上传 {'/'.join(allowed)} 格式构建包。",
            )
        if build.asset.size_bytes > int(
            build_rule.get("max_bytes", 20 * 1024 * 1024)
        ):
            _issue(
                run,
                code="build.file_size",
                message="构建包超过当前规则的体积上限。",
                remediation="清理无用资源并重新构建。",
            )
    incomplete = release.checklist_items.filter(
        is_required=True, is_completed=False
    ).count()
    if incomplete:
        _issue(
            run,
            code="checklist.incomplete",
            message=f"仍有 {incomplete} 个必做检查项未完成。",
            remediation="逐项完成并记录结论。",
        )
    cases = release.test_cases.all()
    if not cases.exists():
        _issue(
            run,
            code="tests.missing",
            message="尚未建立发布测试用例。",
            remediation="至少建立并执行核心业务、授权和失败恢复用例。",
        )
    failed_cases = cases.exclude(result=MiniProgramTestCase.Result.PASSED).count()
    if failed_cases:
        _issue(
            run,
            code="tests.not_passed",
            message=f"仍有 {failed_cases} 个测试用例未通过。",
            remediation="修复失败项并重新执行测试。",
        )
    errors = run.issues.filter(
        severity=MiniProgramValidationIssue.Severity.ERROR
    ).count()
    warnings = run.issues.filter(
        severity=MiniProgramValidationIssue.Severity.WARNING
    ).count()
    run.passed = errors == 0
    run.error_count = errors
    run.warning_count = warnings
    run.summary = {
        "artifact_count": current_artifacts.count(),
        "screenshot_count": screenshots,
        "checklist_total": release.checklist_items.count(),
        "test_case_total": cases.count(),
        "test_case_passed": cases.filter(
            result=MiniProgramTestCase.Result.PASSED
        ).count(),
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
    release: MiniProgramRelease, *, actor=None
) -> MiniProgramExportBundle:
    run = validate_release(release, actor=actor)
    if not run.passed:
        raise ValueError(f"发布 QA 未通过：仍有 {run.error_count} 个错误。")
    release.refresh_from_db()
    artifacts = list(
        release.artifacts.filter(is_current=True).select_related("asset")
    )
    checklist = list(
        release.checklist_items.values(
            "category", "title", "is_required", "is_completed", "note"
        )
    )
    test_cases = list(
        release.test_cases.values(
            "name",
            "steps",
            "expected_result",
            "actual_result",
            "result",
        )
    )
    manifest = {
        "schema": "wx-product.mini-program.release.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "release": {
            "id": str(release.pk),
            "name": release.name,
            "app_id": release.app_id,
            "version": release.version,
            "release_type": release.release_type,
            "change_log": release.change_log,
            "privacy_summary": release.privacy_summary,
        },
        "ruleset": {
            "id": str(run.ruleset_id),
            "version": run.ruleset.version,
            "constraints": run.ruleset.constraints,
        },
        "checklist": checklist,
        "test_cases": test_cases,
        "artifacts": [
            {
                "id": str(artifact.pk),
                "type": artifact.artifact_type,
                "label": artifact.label,
                "filename": artifact.asset.original_name,
                "checksum_sha256": artifact.asset.checksum_sha256,
            }
            for artifact in artifacts
        ],
    }
    output = io.BytesIO()
    type_dirs = {
        MiniProgramArtifact.ArtifactType.BUILD_PACKAGE: "build",
        MiniProgramArtifact.ArtifactType.EXPERIENCE_QR: "experience",
        MiniProgramArtifact.ArtifactType.SCREENSHOT: "screenshots",
        MiniProgramArtifact.ArtifactType.PRIVACY_DOCUMENT: "compliance",
        MiniProgramArtifact.ArtifactType.TEST_EVIDENCE: "tests",
    }
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2)
        )
        archive.writestr(
            "release-notes.txt",
            f"{release.name} {release.version}\n\n{release.change_log}\n",
        )
        archive.writestr(
            "compliance/privacy-summary.txt", release.privacy_summary
        )
        archive.writestr(
            "qa/checklist.json", json.dumps(checklist, ensure_ascii=False, indent=2)
        )
        archive.writestr(
            "qa/test-report.json", json.dumps(test_cases, ensure_ascii=False, indent=2)
        )
        for index, artifact in enumerate(artifacts, start=1):
            directory = type_dirs[artifact.artifact_type]
            filename = Path(artifact.asset.original_name).name
            archive.writestr(
                f"{directory}/{index:02d}-{filename}", read_asset(artifact.asset)
            )
    content = output.getvalue()
    file_asset = create_asset(
        content=content,
        filename=f"mini-program-{release.version}-{release.pk}.zip",
        kind=AssetVersion.Kind.EXPORT,
        source=AssetVersion.Source.EXPORTER,
        actor=actor,
        mime_type="application/zip",
        metadata={"export_schema": manifest["schema"]},
    )
    bundle = MiniProgramExportBundle.objects.create(
        release=release,
        ruleset=run.ruleset,
        file=file_asset,
        manifest=manifest,
        checksum_sha256=file_asset.checksum_sha256,
        created_by=actor,
    )
    if release.status == MiniProgramRelease.Status.QA_REVIEW:
        transition_release(
            release,
            MiniProgramRelease.Status.EXPORT_READY,
            actor=actor,
            note="小程序发布 QA 通过并冻结审核包",
        )
    return bundle
