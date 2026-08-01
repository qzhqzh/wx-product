from pathlib import Path

from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assets.models import AssetVersion
from apps.core.permissions import CanCreate, CanOperate, CanReview

from .models import (
    MiniProgramArtifact,
    MiniProgramChecklistItem,
    MiniProgramRelease,
    MiniProgramSubmission,
    MiniProgramTestCase,
)
from .pipeline import transition_release
from .serializers import (
    MiniProgramArtifactSerializer,
    MiniProgramChecklistSerializer,
    MiniProgramExportSerializer,
    MiniProgramReleaseSerializer,
    MiniProgramSubmissionSerializer,
    MiniProgramTestCaseSerializer,
    MiniProgramValidationRunSerializer,
)
from .services import (
    build_export_bundle,
    create_artifact,
    generate_demo_release,
    validate_release,
)


class ReleaseDetailApi(APIView):
    def get(self, request, release_id):
        release = get_object_or_404(MiniProgramRelease, pk=release_id)
        return Response(MiniProgramReleaseSerializer(release).data)


class PrepareDemoReleaseApi(APIView):
    permission_classes = [CanCreate]

    def post(self, request, release_id):
        release = get_object_or_404(MiniProgramRelease, pk=release_id)
        try:
            generate_demo_release(release, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        release.refresh_from_db()
        return Response(MiniProgramReleaseSerializer(release).data, status=201)


class ArtifactUploadApi(APIView):
    permission_classes = [CanCreate]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, release_id):
        release = get_object_or_404(MiniProgramRelease, pk=release_id)
        uploaded = request.FILES.get("file")
        artifact_type = request.data.get("artifact_type", "")
        if not uploaded:
            return Response({"detail": "请选择文件。"}, status=400)
        if artifact_type not in MiniProgramArtifact.ArtifactType.values:
            return Response({"detail": "未知的产物类型。"}, status=400)
        if uploaded.size > 25 * 1024 * 1024:
            return Response({"detail": "单个文件不能超过 25MB。"}, status=400)
        suffix = Path(uploaded.name).suffix.lower()
        image_types = {
            MiniProgramArtifact.ArtifactType.EXPERIENCE_QR,
            MiniProgramArtifact.ArtifactType.SCREENSHOT,
            MiniProgramArtifact.ArtifactType.TEST_EVIDENCE,
        }
        if artifact_type == MiniProgramArtifact.ArtifactType.BUILD_PACKAGE:
            if suffix != ".zip":
                return Response({"detail": "构建包必须是 ZIP。"}, status=400)
            kind = AssetVersion.Kind.BUILD_PACKAGE
        elif artifact_type in image_types:
            if suffix not in {".png", ".jpg", ".jpeg"}:
                return Response({"detail": "该产物只支持 PNG/JPG/JPEG。"}, status=400)
            kind = (
                AssetVersion.Kind.EXPERIENCE_QR
                if artifact_type == MiniProgramArtifact.ArtifactType.EXPERIENCE_QR
                else AssetVersion.Kind.SCREENSHOT
            )
        else:
            if suffix not in {".pdf", ".txt", ".md"}:
                return Response({"detail": "隐私文档只支持 PDF/TXT/MD。"}, status=400)
            kind = AssetVersion.Kind.DOCUMENT
        artifact = create_artifact(
            release,
            artifact_type=artifact_type,
            label=request.data.get("label") or uploaded.name,
            content=uploaded.read(),
            filename=uploaded.name,
            kind=kind,
            mime_type=uploaded.content_type or "application/octet-stream",
            actor=request.user,
            notes=request.data.get("notes", ""),
            source=AssetVersion.Source.UPLOAD,
        )
        return Response(MiniProgramArtifactSerializer(artifact).data, status=201)


class ChecklistApi(APIView):
    permission_classes = [CanReview]

    def patch(self, request, release_id, item_id):
        item = get_object_or_404(
            MiniProgramChecklistItem, pk=item_id, release_id=release_id
        )
        item.is_completed = bool(request.data.get("is_completed", item.is_completed))
        item.note = request.data.get("note", item.note)
        item.save(update_fields=["is_completed", "note", "updated_at"])
        return Response(MiniProgramChecklistSerializer(item).data)


class TestCaseApi(APIView):
    permission_classes = [CanReview]

    def patch(self, request, release_id, case_id):
        case = get_object_or_404(
            MiniProgramTestCase, pk=case_id, release_id=release_id
        )
        result_value = request.data.get("result", case.result)
        if result_value not in MiniProgramTestCase.Result.values:
            return Response({"detail": "未知的测试结果。"}, status=400)
        case.result = result_value
        case.actual_result = request.data.get("actual_result", case.actual_result)
        case.executed_by = request.user
        case.executed_at = timezone.now()
        case.save(
            update_fields=[
                "result",
                "actual_result",
                "executed_by",
                "executed_at",
                "updated_at",
            ]
        )
        return Response(MiniProgramTestCaseSerializer(case).data)


class ValidateReleaseApi(APIView):
    permission_classes = [CanReview]

    def post(self, request, release_id):
        release = get_object_or_404(MiniProgramRelease, pk=release_id)
        try:
            run = validate_release(release, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(MiniProgramValidationRunSerializer(run).data)


class ExportReleaseApi(APIView):
    permission_classes = [CanOperate]

    def post(self, request, release_id):
        release = get_object_or_404(MiniProgramRelease, pk=release_id)
        try:
            bundle = build_export_bundle(release, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(MiniProgramExportSerializer(bundle).data, status=201)


class ReleaseSubmissionApi(APIView):
    permission_classes = [CanOperate]

    def post(self, request, release_id):
        release = get_object_or_404(MiniProgramRelease, pk=release_id)
        bundle = release.exports.first()
        if not bundle:
            return Response({"detail": "请先生成小程序审核包。"}, status=409)
        submission_status = request.data.get(
            "status", MiniProgramSubmission.Status.SUBMITTED
        )
        if submission_status not in {
            MiniProgramSubmission.Status.SUBMITTED,
            MiniProgramSubmission.Status.IN_REVIEW,
        }:
            return Response({"detail": "新提审只能登记为已提交或审核中。"}, status=400)
        submission = MiniProgramSubmission.objects.create(
            release=release,
            export_bundle=bundle,
            status=submission_status,
            platform_audit_id=request.data.get("platform_audit_id", ""),
            submitted_at=request.data.get("submitted_at") or timezone.now(),
            notes=request.data.get("notes", ""),
            submitted_by=request.user,
        )
        if release.status == MiniProgramRelease.Status.EXPORT_READY:
            transition_release(
                release,
                MiniProgramRelease.Status.SUBMITTED,
                actor=request.user,
                note="已登记微信小程序人工提审",
            )
        return Response(MiniProgramSubmissionSerializer(submission).data, status=201)

    def patch(self, request, release_id):
        release = get_object_or_404(MiniProgramRelease, pk=release_id)
        submission = get_object_or_404(
            MiniProgramSubmission, pk=request.data.get("id"), release=release
        )
        status_value = request.data.get("status", submission.status)
        if status_value not in MiniProgramSubmission.Status.values:
            return Response({"detail": "未知的微信审核状态。"}, status=400)
        allowed_status_changes = {
            MiniProgramSubmission.Status.SUBMITTED: {
                MiniProgramSubmission.Status.SUBMITTED,
                MiniProgramSubmission.Status.IN_REVIEW,
                MiniProgramSubmission.Status.REJECTED,
                MiniProgramSubmission.Status.APPROVED,
            },
            MiniProgramSubmission.Status.IN_REVIEW: {
                MiniProgramSubmission.Status.IN_REVIEW,
                MiniProgramSubmission.Status.REJECTED,
                MiniProgramSubmission.Status.APPROVED,
            },
            MiniProgramSubmission.Status.APPROVED: {
                MiniProgramSubmission.Status.APPROVED,
                MiniProgramSubmission.Status.RELEASED,
            },
            MiniProgramSubmission.Status.REJECTED: {
                MiniProgramSubmission.Status.REJECTED,
            },
            MiniProgramSubmission.Status.RELEASED: {
                MiniProgramSubmission.Status.RELEASED,
            },
        }
        if status_value not in allowed_status_changes.get(submission.status, set()):
            return Response({"detail": "不允许跨越微信审核状态。"}, status=409)
        submission.status = status_value
        submission.platform_audit_id = request.data.get(
            "platform_audit_id", submission.platform_audit_id
        )
        submission.rejection_reason = request.data.get(
            "rejection_reason", submission.rejection_reason
        )
        submission.notes = request.data.get("notes", submission.notes)
        if status_value == MiniProgramSubmission.Status.RELEASED:
            submission.released_at = request.data.get("released_at") or timezone.now()
        submission.save()
        if (
            status_value == MiniProgramSubmission.Status.REJECTED
            and release.status == MiniProgramRelease.Status.SUBMITTED
        ):
            transition_release(
                release,
                MiniProgramRelease.Status.REWORK,
                actor=request.user,
                note=submission.rejection_reason or "微信小程序审核驳回",
            )
        elif (
            status_value == MiniProgramSubmission.Status.APPROVED
            and release.status == MiniProgramRelease.Status.SUBMITTED
        ):
            transition_release(
                release,
                MiniProgramRelease.Status.APPROVED,
                actor=request.user,
                note="微信小程序审核通过",
            )
        elif (
            status_value == MiniProgramSubmission.Status.RELEASED
            and release.status == MiniProgramRelease.Status.APPROVED
        ):
            transition_release(
                release,
                MiniProgramRelease.Status.RELEASED,
                actor=request.user,
                note="微信小程序版本已发布",
            )
        return Response(MiniProgramSubmissionSerializer(submission).data)
