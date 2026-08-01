from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.assets.models import AssetVersion
from apps.assets.services import create_asset, normalize_static_asset
from apps.core.permissions import CanCreate, CanOperate, CanReview

from .models import (
    RedPacketCampaign,
    RedPacketDesign,
    RedPacketDistribution,
    RedPacketOrder,
    RedPacketSubmission,
)
from .pipeline import transition_campaign
from .serializers import (
    RedPacketCampaignSerializer,
    RedPacketDesignSerializer,
    RedPacketExportSerializer,
    RedPacketOrderSerializer,
    RedPacketSubmissionSerializer,
    RedPacketValidationRunSerializer,
)
from .services import (
    approve_selected_design,
    build_export_bundle,
    generate_demo_designs,
    get_ruleset,
    select_design,
    validate_campaign,
)


class CampaignDetailApi(APIView):
    def get(self, request, campaign_id):
        campaign = get_object_or_404(RedPacketCampaign, pk=campaign_id)
        return Response(RedPacketCampaignSerializer(campaign).data)


class GenerateDesignsApi(APIView):
    permission_classes = [CanCreate]

    def post(self, request, campaign_id):
        campaign = get_object_or_404(RedPacketCampaign, pk=campaign_id)
        try:
            designs = generate_demo_designs(campaign, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(RedPacketDesignSerializer(designs, many=True).data, status=201)


class UploadDesignApi(APIView):
    permission_classes = [CanCreate]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, campaign_id):
        campaign = get_object_or_404(RedPacketCampaign, pk=campaign_id)
        uploaded = request.FILES.get("file")
        if not uploaded:
            return Response({"detail": "请选择封面文件。"}, status=400)
        if uploaded.size > 20 * 1024 * 1024:
            return Response({"detail": "源文件不能超过 20MB。"}, status=400)
        suffix = uploaded.name.lower().rsplit(".", 1)[-1]
        if suffix not in {"png", "jpg", "jpeg"}:
            return Response({"detail": "只支持 PNG、JPG 或 JPEG。"}, status=400)
        raw = create_asset(
            content=uploaded.read(),
            filename=uploaded.name,
            kind=AssetVersion.Kind.SOURCE,
            source=AssetVersion.Source.UPLOAD,
            actor=request.user,
            mime_type=uploaded.content_type or "",
        )
        ruleset = get_ruleset(campaign)
        size = tuple(ruleset.constraints.get("cover", {}).get("size", [957, 1278]))
        final = normalize_static_asset(
            raw,
            actor=request.user,
            size=size,
            kind=AssetVersion.Kind.RED_PACKET_COVER,
        )
        order = (campaign.designs.aggregate(value=Max("order"))["value"] or 0) + 1
        design = RedPacketDesign.objects.create(
            campaign=campaign,
            order=order,
            title=request.data.get("title") or f"人工方案 {order}",
            prompt="人工上传",
            asset=final,
        )
        if campaign.status == RedPacketCampaign.Status.DRAFT:
            campaign = transition_campaign(
                campaign,
                RedPacketCampaign.Status.BRIEF_APPROVED,
                actor=request.user,
                note="通过上传封面确认 Brief",
            )
        if campaign.status in {
            RedPacketCampaign.Status.BRIEF_APPROVED,
            RedPacketCampaign.Status.REWORK,
        }:
            campaign = transition_campaign(
                campaign,
                RedPacketCampaign.Status.DESIGNING,
                actor=request.user,
                note="上传封面方案",
            )
        if campaign.status == RedPacketCampaign.Status.DESIGNING:
            transition_campaign(
                campaign,
                RedPacketCampaign.Status.CREATIVE_REVIEW,
                actor=request.user,
                note="人工封面方案待审",
            )
        return Response(RedPacketDesignSerializer(design).data, status=201)


class SelectDesignApi(APIView):
    permission_classes = [CanCreate]

    def post(self, request, campaign_id, design_id):
        design = get_object_or_404(
            RedPacketDesign, pk=design_id, campaign_id=campaign_id
        )
        return Response(
            RedPacketDesignSerializer(
                select_design(design, actor=request.user)
            ).data
        )


class ApproveDesignApi(APIView):
    permission_classes = [CanReview]

    def post(self, request, campaign_id):
        campaign = get_object_or_404(RedPacketCampaign, pk=campaign_id)
        try:
            design = approve_selected_design(
                campaign,
                actor=request.user,
                note=request.data.get("note", ""),
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(RedPacketDesignSerializer(design).data)


class ValidateCampaignApi(APIView):
    permission_classes = [CanReview]

    def post(self, request, campaign_id):
        campaign = get_object_or_404(RedPacketCampaign, pk=campaign_id)
        try:
            run = validate_campaign(campaign, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(RedPacketValidationRunSerializer(run).data)


class ExportCampaignApi(APIView):
    permission_classes = [CanOperate]

    def post(self, request, campaign_id):
        campaign = get_object_or_404(RedPacketCampaign, pk=campaign_id)
        try:
            bundle = build_export_bundle(campaign, actor=request.user)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=409)
        return Response(RedPacketExportSerializer(bundle).data, status=201)


class CampaignSubmissionApi(APIView):
    permission_classes = [CanOperate]

    def post(self, request, campaign_id):
        campaign = get_object_or_404(RedPacketCampaign, pk=campaign_id)
        bundle = campaign.exports.first()
        if not bundle:
            return Response({"detail": "请先生成红包封面投稿包。"}, status=409)
        submission_status = request.data.get(
            "status", RedPacketSubmission.Status.SUBMITTED
        )
        if submission_status not in {
            RedPacketSubmission.Status.SUBMITTED,
            RedPacketSubmission.Status.IN_REVIEW,
        }:
            return Response({"detail": "新提交只能登记为已提交或审核中。"}, status=400)
        submission = RedPacketSubmission.objects.create(
            campaign=campaign,
            export_bundle=bundle,
            status=submission_status,
            platform_work_id=request.data.get("platform_work_id", ""),
            submitted_at=request.data.get("submitted_at") or timezone.now(),
            notes=request.data.get("notes", ""),
            submitted_by=request.user,
        )
        if campaign.status == RedPacketCampaign.Status.EXPORT_READY:
            transition_campaign(
                campaign,
                RedPacketCampaign.Status.SUBMITTED,
                actor=request.user,
                note="已登记微信红包封面人工提交",
            )
        return Response(RedPacketSubmissionSerializer(submission).data, status=201)

    def patch(self, request, campaign_id):
        campaign = get_object_or_404(RedPacketCampaign, pk=campaign_id)
        submission = get_object_or_404(
            RedPacketSubmission, pk=request.data.get("id"), campaign=campaign
        )
        status_value = request.data.get("status", submission.status)
        if status_value not in RedPacketSubmission.Status.values:
            return Response({"detail": "未知的审核状态。"}, status=400)
        submission.status = status_value
        submission.platform_work_id = request.data.get(
            "platform_work_id", submission.platform_work_id
        )
        submission.rejection_reason = request.data.get(
            "rejection_reason", submission.rejection_reason
        )
        submission.notes = request.data.get("notes", submission.notes)
        submission.save()
        if (
            status_value == RedPacketSubmission.Status.REJECTED
            and campaign.status == RedPacketCampaign.Status.SUBMITTED
        ):
            transition_campaign(
                campaign,
                RedPacketCampaign.Status.REWORK,
                actor=request.user,
                note=submission.rejection_reason or "微信红包封面审核驳回",
            )
        elif (
            status_value == RedPacketSubmission.Status.APPROVED
            and campaign.status == RedPacketCampaign.Status.SUBMITTED
        ):
            transition_campaign(
                campaign,
                RedPacketCampaign.Status.APPROVED,
                actor=request.user,
                note="微信红包封面审核通过",
            )
        return Response(RedPacketSubmissionSerializer(submission).data)


class CampaignOrderApi(APIView):
    permission_classes = [CanOperate]

    def post(self, request, campaign_id):
        campaign = get_object_or_404(RedPacketCampaign, pk=campaign_id)
        if campaign.status not in {
            RedPacketCampaign.Status.APPROVED,
            RedPacketCampaign.Status.DISTRIBUTING,
        }:
            return Response({"detail": "微信审核通过后才能登记下单。"}, status=409)
        quantity = int(request.data.get("quantity", 0))
        if quantity <= 0:
            return Response({"detail": "下单数量必须大于 0。"}, status=400)
        order_status = request.data.get("status", RedPacketOrder.Status.AVAILABLE)
        if order_status not in {
            RedPacketOrder.Status.PLANNED,
            RedPacketOrder.Status.PURCHASED,
            RedPacketOrder.Status.AVAILABLE,
        }:
            return Response({"detail": "新订单状态必须是待下单、已下单或可发放。"}, status=400)
        order = RedPacketOrder.objects.create(
            campaign=campaign,
            platform_order_no=request.data.get("platform_order_no", ""),
            quantity=quantity,
            unit_cost=request.data.get("unit_cost") or 0,
            status=order_status,
            purchased_at=request.data.get("purchased_at") or timezone.now(),
            expires_at=request.data.get("expires_at") or None,
            notes=request.data.get("notes", ""),
            created_by=request.user,
        )
        if campaign.status == RedPacketCampaign.Status.APPROVED:
            transition_campaign(
                campaign,
                RedPacketCampaign.Status.DISTRIBUTING,
                actor=request.user,
                note=f"已登记 {quantity} 份红包封面库存",
            )
        return Response(RedPacketOrderSerializer(order).data, status=201)


class DistributionApi(APIView):
    permission_classes = [CanOperate]

    @transaction.atomic
    def post(self, request, campaign_id, order_id):
        order = get_object_or_404(
            RedPacketOrder.objects.select_for_update(),
            pk=order_id,
            campaign_id=campaign_id,
        )
        quantity = int(request.data.get("quantity", 0))
        if quantity <= 0 or quantity > order.available_quantity:
            return Response(
                {"detail": f"发放数量应在 1 到 {order.available_quantity} 之间。"},
                status=400,
            )
        RedPacketDistribution.objects.create(
            order=order,
            channel=request.data.get("channel") or "人工发放",
            quantity=quantity,
            distributed_at=request.data.get("distributed_at") or timezone.now(),
            notes=request.data.get("notes", ""),
            created_by=request.user,
        )
        if order.available_quantity == 0:
            order.status = RedPacketOrder.Status.EXHAUSTED
            order.save(update_fields=["status", "updated_at"])
        campaign = order.campaign
        if (
            campaign.orders.exists()
            and not campaign.orders.exclude(status=RedPacketOrder.Status.EXHAUSTED).exists()
            and campaign.status == RedPacketCampaign.Status.DISTRIBUTING
        ):
            transition_campaign(
                campaign,
                RedPacketCampaign.Status.COMPLETED,
                actor=request.user,
                note="全部红包封面库存已发放",
            )
        return Response(RedPacketOrderSerializer(order).data, status=201)
