from django.db import transaction

from apps.core.models import TransitionEvent

from .models import RedPacketApprovalRecord, RedPacketCampaign

ALLOWED_TRANSITIONS = {
    RedPacketCampaign.Status.DRAFT: {
        RedPacketCampaign.Status.BRIEF_APPROVED,
        RedPacketCampaign.Status.ARCHIVED,
    },
    RedPacketCampaign.Status.BRIEF_APPROVED: {
        RedPacketCampaign.Status.DESIGNING,
        RedPacketCampaign.Status.REWORK,
    },
    RedPacketCampaign.Status.DESIGNING: {
        RedPacketCampaign.Status.CREATIVE_REVIEW,
        RedPacketCampaign.Status.REWORK,
    },
    RedPacketCampaign.Status.CREATIVE_REVIEW: {
        RedPacketCampaign.Status.RIGHTS_REVIEW,
        RedPacketCampaign.Status.REWORK,
    },
    RedPacketCampaign.Status.RIGHTS_REVIEW: {
        RedPacketCampaign.Status.QA_REVIEW,
        RedPacketCampaign.Status.REWORK,
    },
    RedPacketCampaign.Status.QA_REVIEW: {
        RedPacketCampaign.Status.EXPORT_READY,
        RedPacketCampaign.Status.REWORK,
    },
    RedPacketCampaign.Status.EXPORT_READY: {
        RedPacketCampaign.Status.SUBMITTED,
        RedPacketCampaign.Status.REWORK,
    },
    RedPacketCampaign.Status.SUBMITTED: {
        RedPacketCampaign.Status.APPROVED,
        RedPacketCampaign.Status.REWORK,
    },
    RedPacketCampaign.Status.APPROVED: {
        RedPacketCampaign.Status.DISTRIBUTING,
        RedPacketCampaign.Status.ARCHIVED,
    },
    RedPacketCampaign.Status.DISTRIBUTING: {
        RedPacketCampaign.Status.COMPLETED,
        RedPacketCampaign.Status.REWORK,
    },
    RedPacketCampaign.Status.COMPLETED: {RedPacketCampaign.Status.ARCHIVED},
    RedPacketCampaign.Status.REWORK: {
        RedPacketCampaign.Status.DESIGNING,
        RedPacketCampaign.Status.CREATIVE_REVIEW,
        RedPacketCampaign.Status.RIGHTS_REVIEW,
        RedPacketCampaign.Status.QA_REVIEW,
        RedPacketCampaign.Status.ARCHIVED,
    },
    RedPacketCampaign.Status.ARCHIVED: set(),
}


@transaction.atomic
def transition_campaign(
    campaign: RedPacketCampaign, to_state: str, *, actor=None, note: str = ""
):
    locked = RedPacketCampaign.objects.select_for_update().get(pk=campaign.pk)
    if to_state == locked.status:
        return locked
    if to_state not in ALLOWED_TRANSITIONS.get(locked.status, set()):
        raise ValueError(f"不允许从“{locked.get_status_display()}”进入目标状态。")
    from_state = locked.status
    locked.status = to_state
    locked.save(update_fields=["status", "updated_at"])
    TransitionEvent.objects.create(
        object_type="red_packet_campaign",
        object_id=locked.pk,
        from_state=from_state,
        to_state=to_state,
        action="transition",
        note=note,
        actor=actor,
    )
    if to_state in {
        RedPacketCampaign.Status.BRIEF_APPROVED,
        RedPacketCampaign.Status.RIGHTS_REVIEW,
        RedPacketCampaign.Status.EXPORT_READY,
        RedPacketCampaign.Status.APPROVED,
    }:
        RedPacketApprovalRecord.objects.create(
            campaign=locked,
            stage=to_state,
            decision=RedPacketApprovalRecord.Decision.APPROVED,
            note=note,
            actor=actor,
        )
    if to_state == RedPacketCampaign.Status.REWORK:
        RedPacketApprovalRecord.objects.create(
            campaign=locked,
            stage=from_state,
            decision=RedPacketApprovalRecord.Decision.REJECTED,
            note=note,
            actor=actor,
        )
    return locked
