from django.utils import timezone
from rest_framework.exceptions import APIException

from .export_integrity import export_is_current


class PipelineConflict(APIException):
    status_code = 409
    default_code = "pipeline_conflict"


EMOJI_CONTENT_MUTATIONS = {
    "PlanPackApi",
    "GenerateAllApi",
    "GenerateItemApi",
    "ItemPromptApi",
    "PackPromptPresetApi",
    "ItemSelectionApi",
    "ItemApprovalApi",
    "ItemUploadApi",
    "GenerateFramesApi",
    "SequenceApi",
    "ValidatePackApi",
    "ExportPackApi",
}
RED_PACKET_CONTENT_MUTATIONS = {
    "GenerateDesignsApi",
    "UploadDesignApi",
    "SelectDesignApi",
    "ApproveDesignApi",
    "ValidateCampaignApi",
    "ExportCampaignApi",
}
MINI_PROGRAM_CONTENT_MUTATIONS = {
    "PrepareDemoReleaseApi",
    "ArtifactUploadApi",
    "ChecklistApi",
    "TestCaseApi",
    "ValidateReleaseApi",
    "ExportReleaseApi",
}


def _ensure_current_export(view_name: str, view) -> None:
    if view_name == "SubmissionApi":
        from apps.emoji.models import EmojiPack

        parent = EmojiPack.objects.filter(pk=view.kwargs.get("pack_id")).first()
        export = parent.exports.first() if parent else None
    elif view_name == "CampaignSubmissionApi":
        from apps.redpacket.models import RedPacketCampaign

        parent = RedPacketCampaign.objects.filter(
            pk=view.kwargs.get("campaign_id")
        ).first()
        export = parent.exports.first() if parent else None
    elif view_name == "ReleaseSubmissionApi":
        from apps.miniprogram.models import MiniProgramRelease

        parent = MiniProgramRelease.objects.filter(
            pk=view.kwargs.get("release_id")
        ).first()
        export = parent.exports.first() if parent else None
    else:
        return

    if export is not None and not export_is_current(export):
        raise PipelineConflict(
            "上游内容已在导出后发生变化，请重新执行 QA 并生成审核包。"
        )


def _ensure_mutable(view_name: str, view) -> None:
    if view_name in EMOJI_CONTENT_MUTATIONS:
        from apps.emoji.models import EmojiPack

        parent = EmojiPack.objects.filter(pk=view.kwargs.get("pack_id")).first()
        terminal = {
            EmojiPack.Status.SUBMITTED,
            EmojiPack.Status.PUBLISHED,
            EmojiPack.Status.ARCHIVED,
        }
    elif view_name in RED_PACKET_CONTENT_MUTATIONS:
        from apps.redpacket.models import RedPacketCampaign

        parent = RedPacketCampaign.objects.filter(
            pk=view.kwargs.get("campaign_id")
        ).first()
        terminal = {
            RedPacketCampaign.Status.SUBMITTED,
            RedPacketCampaign.Status.APPROVED,
            RedPacketCampaign.Status.DISTRIBUTING,
            RedPacketCampaign.Status.COMPLETED,
            RedPacketCampaign.Status.ARCHIVED,
        }
    elif view_name in MINI_PROGRAM_CONTENT_MUTATIONS:
        from apps.miniprogram.models import MiniProgramRelease

        parent = MiniProgramRelease.objects.filter(
            pk=view.kwargs.get("release_id")
        ).first()
        terminal = {
            MiniProgramRelease.Status.SUBMITTED,
            MiniProgramRelease.Status.APPROVED,
            MiniProgramRelease.Status.RELEASED,
            MiniProgramRelease.Status.ARCHIVED,
        }
    else:
        return

    if parent is not None and parent.status in terminal:
        raise PipelineConflict("该对象已经提交或进入终态，请建立返修或新版本后再修改。")


def _ensure_distribution_allowed(view) -> None:
    from apps.redpacket.models import RedPacketCampaign, RedPacketOrder

    order = (
        RedPacketOrder.objects.select_related("campaign")
        .filter(
            pk=view.kwargs.get("order_id"),
            campaign_id=view.kwargs.get("campaign_id"),
        )
        .first()
    )
    if order is None:
        return
    if order.campaign.status != RedPacketCampaign.Status.DISTRIBUTING:
        raise PipelineConflict("红包封面活动不处于发放中状态。")
    if order.status != RedPacketOrder.Status.AVAILABLE:
        raise PipelineConflict("只有可发放状态的订单才能扣减库存。")
    if order.expires_at and order.expires_at <= timezone.now():
        raise PipelineConflict("该红包封面订单已经过期，不能继续发放。")


def enforce_runtime_constraints(request, view) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return
    view_name = view.__class__.__name__
    _ensure_mutable(view_name, view)
    if request.method == "POST":
        _ensure_current_export(view_name, view)
        if view_name == "DistributionApi":
            _ensure_distribution_allowed(view)
