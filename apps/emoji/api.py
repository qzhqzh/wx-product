from uuid import UUID

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assets.models import AssetVersion
from apps.assets.services import create_asset, normalize_static_asset

from .models import (
    AnimationFrame,
    EmojiItem,
    EmojiPack,
    MetricSnapshot,
    PromptPreset,
    SubmissionRecord,
)
from .permissions import CanCreate, CanOperate, CanReview
from .pipeline import transition_pack
from .serializers import (
    EmojiItemSerializer,
    JobSerializer,
    PackSerializer,
    SubmissionSerializer,
    ValidationRunSerializer,
)
from .services import build_export_bundle, validate_pack
from .tasks import (
    enqueue_assemble_job,
    enqueue_frames_job,
    enqueue_image_job,
    enqueue_plan_job,
    enqueue_prompt_job,
)


class PackDetailApi(APIView):
    def get(self, request, pack_id):
        pack = get_object_or_404(EmojiPack, pk=pack_id)
        return Response(PackSerializer(pack).data)


class PlanPackApi(APIView):
    permission_classes = [CanCreate]

    def post(self, request, pack_id):
        pack = get_object_or_404(EmojiPack, pk=pack_id)
        provider = request.data.get("provider", "local")
        if pack.status == EmojiPack.Status.DRAFT:
            pack = transition_pack(
                pack,
                EmojiPack.Status.BRIEF_APPROVED,
                actor=request.user,
                note="通过工作台确认 Brief",
            )
        job = enqueue_plan_job(pack, provider=provider, actor=request.user)
        return Response(JobSerializer(job).data, status=202)


class GenerateAllApi(APIView):
    permission_classes = [CanCreate]

    def post(self, request, pack_id):
        pack = get_object_or_404(EmojiPack, pk=pack_id)
        provider = request.data.get("provider", "local")
        jobs = [
            enqueue_image_job(item, provider=provider, actor=request.user)
            for item in pack.items.all()
        ]
        return Response(JobSerializer(jobs, many=True).data, status=202)


class GenerateItemApi(APIView):
    permission_classes = [CanCreate]

    def post(self, request, pack_id, item_id):
        item = get_object_or_404(EmojiItem, pk=item_id, pack_id=pack_id)
        provider = request.data.get("provider", "local")
        job = enqueue_image_job(item, provider=provider, actor=request.user)
        return Response(JobSerializer(job).data, status=202)


class ItemPromptApi(APIView):
    permission_classes = [CanCreate]

    def patch(self, request, pack_id, item_id):
        item = get_object_or_404(EmojiItem, pk=item_id, pack_id=pack_id)
        prompt = str(request.data.get("prompt", "")).strip()
        if not prompt:
            return Response({"detail": "提示词不能为空。"}, status=400)
        if len(prompt) > 4000:
            return Response({"detail": "提示词不能超过 4000 个字符。"}, status=400)
        item.prompt = prompt
        item.save(update_fields=["prompt", "updated_at"])
        return Response(EmojiItemSerializer(item).data)

    def post(self, request, pack_id, item_id):
        item = get_object_or_404(EmojiItem, pk=item_id, pack_id=pack_id)
        provider = request.data.get("provider", "qwen")
        if provider not in {"local", "openai", "qwen"}:
            return Response({"detail": "不支持该提示词优化模型。"}, status=400)
        prompt = str(request.data.get("prompt", item.prompt)).strip()
        if not prompt:
            return Response({"detail": "提示词不能为空。"}, status=400)
        if len(prompt) > 4000:
            return Response({"detail": "提示词不能超过 4000 个字符。"}, status=400)
        if prompt != item.prompt:
            item.prompt = prompt
            item.save(update_fields=["prompt", "updated_at"])
        job = enqueue_prompt_job(item, provider=provider, actor=request.user)
        return Response(JobSerializer(job).data, status=202)


class PackPromptPresetApi(APIView):
    permission_classes = [CanCreate]

    def patch(self, request, pack_id):
        pack = get_object_or_404(EmojiPack, pk=pack_id)
        preset_ids = request.data.get("preset_ids", [])
        if not isinstance(preset_ids, list):
            return Response({"detail": "preset_ids 必须是列表。"}, status=400)
        if any(not isinstance(preset_id, str) for preset_id in preset_ids):
            return Response({"detail": "提示词 ID 格式不正确。"}, status=400)
        try:
            normalized_ids = {str(UUID(preset_id)) for preset_id in preset_ids}
        except ValueError:
            return Response({"detail": "提示词 ID 格式不正确。"}, status=400)
        presets = list(PromptPreset.objects.filter(pk__in=normalized_ids, is_active=True))
        if len(presets) != len(normalized_ids):
            return Response({"detail": "存在无效或已停用的提示词。"}, status=400)
        pack.prompt_presets.set(presets)
        return Response(PackSerializer(pack).data)


class ItemSelectionApi(APIView):
    permission_classes = [CanCreate]

    def post(self, request, pack_id, item_id):
        item = get_object_or_404(EmojiItem, pk=item_id, pack_id=pack_id)
        asset = get_object_or_404(AssetVersion, pk=request.data.get("asset_id"))
        if not item.candidates.filter(pk=asset.pk).exists():
            return Response({"detail": "该素材不属于当前表情候选。"}, status=400)
        item.selected_asset = asset
        item.save(update_fields=["selected_asset", "updated_at"])
        return Response(EmojiItemSerializer(item).data)


class ItemApprovalApi(APIView):
    permission_classes = [CanReview]

    def post(self, request, pack_id, item_id):
        item = get_object_or_404(EmojiItem, pk=item_id, pack_id=pack_id)
        item.is_approved = bool(request.data.get("approved", True))
        item.review_note = request.data.get("note", "")
        item.save(update_fields=["is_approved", "review_note", "updated_at"])
        pack = item.pack
        ready = (
            pack.items.count() == pack.target_count
            and not pack.items.filter(is_approved=False).exists()
            and not pack.items.filter(selected_asset=None).exists()
        )
        if ready:
            if pack.status == EmojiPack.Status.GENERATING:
                pack = transition_pack(
                    pack,
                    EmojiPack.Status.CREATIVE_REVIEW,
                    actor=request.user,
                    note="全部素材已生成",
                )
            if pack.status == EmojiPack.Status.CREATIVE_REVIEW:
                transition_pack(
                    pack,
                    EmojiPack.Status.PROCESSING,
                    actor=request.user,
                    note="全部表情已完成创意确认",
                )
        return Response(EmojiItemSerializer(item).data)


class ItemUploadApi(APIView):
    permission_classes = [CanCreate]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pack_id, item_id):
        item = get_object_or_404(EmojiItem, pk=item_id, pack_id=pack_id)
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"detail": "请选择文件。"}, status=400)
        if uploaded.size > 20 * 1024 * 1024:
            return Response({"detail": "源文件不能超过 20MB。"}, status=400)
        content = uploaded.read()
        suffix = uploaded.name.lower().rsplit(".", 1)[-1]
        if suffix not in {"png", "jpg", "jpeg", "gif"}:
            return Response({"detail": "只支持 PNG、JPG、JPEG 或 GIF。"}, status=400)
        raw = create_asset(
            content=content,
            filename=uploaded.name,
            kind=AssetVersion.Kind.SOURCE,
            source=AssetVersion.Source.UPLOAD,
            actor=request.user,
            mime_type=uploaded.content_type or "",
        )
        if suffix == "gif" and raw.frame_count > 1:
            final = raw
        else:
            final = normalize_static_asset(raw, actor=request.user)
        item.candidates.add(raw, final)
        item.selected_asset = final
        item.save(update_fields=["selected_asset", "updated_at"])
        return Response(EmojiItemSerializer(item).data, status=201)


class GenerateFramesApi(APIView):
    permission_classes = [CanCreate]

    def post(self, request, pack_id, item_id):
        item = get_object_or_404(EmojiItem, pk=item_id, pack_id=pack_id)
        count = int(request.data.get("frame_count", 6))
        job = enqueue_frames_job(item, frame_count=count, actor=request.user)
        return Response(JobSerializer(job).data, status=202)


class SequenceApi(APIView):
    permission_classes = [CanCreate]

    def patch(self, request, pack_id, item_id):
        item = get_object_or_404(EmojiItem, pk=item_id, pack_id=pack_id)
        from .models import AnimationSequence

        sequence = get_object_or_404(AnimationSequence, item=item)
        frame_updates = request.data.get("frames", [])
        current_frames = list(sequence.frames.all())
        current_by_id = {str(frame.pk): frame for frame in current_frames}
        requested_ids = [str(frame_data.get("id", "")) for frame_data in frame_updates]
        if len(requested_ids) != len(set(requested_ids)) or set(requested_ids) != set(
            current_by_id
        ):
            return Response({"detail": "必须提交该序列的全部帧，且不能重复。"}, status=400)
        with transaction.atomic():
            for frame in current_frames:
                frame.order += 1000
            AnimationFrame.objects.bulk_update(current_frames, ["order"])
            for index, frame_data in enumerate(frame_updates, start=1):
                frame = current_by_id[str(frame_data["id"])]
                frame.order = index
                frame.duration_ms = max(40, min(int(frame_data.get("duration_ms", 120)), 2000))
            AnimationFrame.objects.bulk_update(
                [current_by_id[frame_id] for frame_id in requested_ids],
                ["order", "duration_ms", "updated_at"],
            )
            if "loop_count" in request.data:
                sequence.loop_count = max(0, int(request.data["loop_count"]))
            sequence.save(update_fields=["loop_count", "updated_at"])
        job = enqueue_assemble_job(sequence, actor=request.user)
        return Response(JobSerializer(job).data, status=202)


class ValidatePackApi(APIView):
    permission_classes = [CanReview]

    def post(self, request, pack_id):
        pack = get_object_or_404(EmojiPack, pk=pack_id)
        run = validate_pack(pack, actor=request.user)
        return Response(ValidationRunSerializer(run).data)


class ExportPackApi(APIView):
    permission_classes = [CanOperate]

    def post(self, request, pack_id):
        pack = get_object_or_404(EmojiPack, pk=pack_id)
        try:
            bundle = build_export_bundle(pack, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        from .serializers import ExportBundleSerializer

        return Response(ExportBundleSerializer(bundle).data, status=201)


class TransitionPackApi(APIView):
    permission_classes = [CanReview]

    def post(self, request, pack_id):
        pack = get_object_or_404(EmojiPack, pk=pack_id)
        try:
            pack = transition_pack(
                pack,
                request.data.get("to_state"),
                actor=request.user,
                note=request.data.get("note", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(PackSerializer(pack).data)


class SubmissionApi(APIView):
    permission_classes = [CanOperate]

    def post(self, request, pack_id):
        pack = get_object_or_404(EmojiPack, pk=pack_id)
        export = pack.exports.first()
        if not export:
            return Response({"detail": "请先生成投稿包。"}, status=409)
        submission_status = request.data.get(
            "status", SubmissionRecord.Status.SUBMITTED
        )
        if submission_status not in {
            SubmissionRecord.Status.SUBMITTED,
            SubmissionRecord.Status.IN_REVIEW,
        }:
            return Response({"detail": "新投稿只能登记为已提交或审核中。"}, status=400)
        submission = SubmissionRecord.objects.create(
            pack=pack,
            export_bundle=export,
            status=submission_status,
            platform_work_id=request.data.get("platform_work_id", ""),
            submitted_at=request.data.get("submitted_at") or timezone.now(),
            scheduled_publish_at=request.data.get("scheduled_publish_at") or None,
            rejection_reason=request.data.get("rejection_reason", ""),
            notes=request.data.get("notes", ""),
            submitted_by=request.user,
        )
        if pack.status == EmojiPack.Status.EXPORT_READY:
            transition_pack(
                pack,
                EmojiPack.Status.SUBMITTED,
                actor=request.user,
                note="已登记微信人工投稿",
            )
        return Response(SubmissionSerializer(submission).data, status=201)

    def patch(self, request, pack_id):
        pack = get_object_or_404(EmojiPack, pk=pack_id)
        submission = get_object_or_404(SubmissionRecord, pk=request.data.get("id"), pack=pack)
        if (
            "status" in request.data
            and request.data["status"] not in SubmissionRecord.Status.values
        ):
            return Response({"detail": "未知的平台投稿状态。"}, status=400)
        for field in ("status", "platform_work_id", "rejection_reason", "notes"):
            if field in request.data:
                setattr(submission, field, request.data[field] or "")
        if "scheduled_publish_at" in request.data:
            submission.scheduled_publish_at = request.data["scheduled_publish_at"] or None
        submission.save()
        if submission.status == SubmissionRecord.Status.REJECTED:
            if pack.status == EmojiPack.Status.SUBMITTED:
                transition_pack(
                    pack,
                    EmojiPack.Status.REWORK,
                    actor=request.user,
                    note=submission.rejection_reason or "微信审核驳回",
                )
        elif submission.status in {
            SubmissionRecord.Status.APPROVED,
            SubmissionRecord.Status.PUBLISHED,
        }:
            if pack.status == EmojiPack.Status.SUBMITTED:
                transition_pack(
                    pack,
                    EmojiPack.Status.PUBLISHED,
                    actor=request.user,
                    note="微信审核通过",
                )
        return Response(SubmissionSerializer(submission).data)


class MetricApi(APIView):
    permission_classes = [CanOperate]

    def post(self, request, pack_id):
        pack = get_object_or_404(EmojiPack, pk=pack_id)
        snapshot, _ = MetricSnapshot.objects.update_or_create(
            pack=pack,
            captured_on=request.data.get("captured_on") or timezone.localdate(),
            source=request.data.get("source", "manual"),
            defaults={
                "metrics": request.data.get("metrics", {}),
                "created_by": request.user,
            },
        )
        return Response(
            {
                "id": snapshot.pk,
                "captured_on": snapshot.captured_on,
                "source": snapshot.source,
                "metrics": snapshot.metrics,
            },
            status=201,
        )
