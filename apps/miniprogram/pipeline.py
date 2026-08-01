from django.db import transaction

from apps.core.models import TransitionEvent

from .models import MiniProgramApprovalRecord, MiniProgramRelease

ALLOWED_TRANSITIONS = {
    MiniProgramRelease.Status.DRAFT: {
        MiniProgramRelease.Status.PRD_APPROVED,
        MiniProgramRelease.Status.ARCHIVED,
    },
    MiniProgramRelease.Status.PRD_APPROVED: {
        MiniProgramRelease.Status.DEVELOPING,
        MiniProgramRelease.Status.REWORK,
    },
    MiniProgramRelease.Status.DEVELOPING: {
        MiniProgramRelease.Status.BUILD_READY,
        MiniProgramRelease.Status.REWORK,
    },
    MiniProgramRelease.Status.BUILD_READY: {
        MiniProgramRelease.Status.EXPERIENCE_REVIEW,
        MiniProgramRelease.Status.REWORK,
    },
    MiniProgramRelease.Status.EXPERIENCE_REVIEW: {
        MiniProgramRelease.Status.COMPLIANCE_REVIEW,
        MiniProgramRelease.Status.REWORK,
    },
    MiniProgramRelease.Status.COMPLIANCE_REVIEW: {
        MiniProgramRelease.Status.QA_REVIEW,
        MiniProgramRelease.Status.REWORK,
    },
    MiniProgramRelease.Status.QA_REVIEW: {
        MiniProgramRelease.Status.EXPORT_READY,
        MiniProgramRelease.Status.REWORK,
    },
    MiniProgramRelease.Status.EXPORT_READY: {
        MiniProgramRelease.Status.SUBMITTED,
        MiniProgramRelease.Status.REWORK,
    },
    MiniProgramRelease.Status.SUBMITTED: {
        MiniProgramRelease.Status.APPROVED,
        MiniProgramRelease.Status.REWORK,
    },
    MiniProgramRelease.Status.APPROVED: {
        MiniProgramRelease.Status.RELEASED,
        MiniProgramRelease.Status.REWORK,
    },
    MiniProgramRelease.Status.RELEASED: {MiniProgramRelease.Status.ARCHIVED},
    MiniProgramRelease.Status.REWORK: {
        MiniProgramRelease.Status.DEVELOPING,
        MiniProgramRelease.Status.BUILD_READY,
        MiniProgramRelease.Status.EXPERIENCE_REVIEW,
        MiniProgramRelease.Status.COMPLIANCE_REVIEW,
        MiniProgramRelease.Status.QA_REVIEW,
        MiniProgramRelease.Status.ARCHIVED,
    },
    MiniProgramRelease.Status.ARCHIVED: set(),
}


@transaction.atomic
def transition_release(
    release: MiniProgramRelease, to_state: str, *, actor=None, note: str = ""
):
    locked = MiniProgramRelease.objects.select_for_update().get(pk=release.pk)
    if to_state == locked.status:
        return locked
    if to_state not in ALLOWED_TRANSITIONS.get(locked.status, set()):
        raise ValueError(f"不允许从“{locked.get_status_display()}”进入目标状态。")
    from_state = locked.status
    locked.status = to_state
    locked.save(update_fields=["status", "updated_at"])
    TransitionEvent.objects.create(
        object_type="mini_program_release",
        object_id=locked.pk,
        from_state=from_state,
        to_state=to_state,
        action="transition",
        note=note,
        actor=actor,
    )
    if to_state in {
        MiniProgramRelease.Status.PRD_APPROVED,
        MiniProgramRelease.Status.EXPERIENCE_REVIEW,
        MiniProgramRelease.Status.COMPLIANCE_REVIEW,
        MiniProgramRelease.Status.EXPORT_READY,
        MiniProgramRelease.Status.APPROVED,
    }:
        MiniProgramApprovalRecord.objects.create(
            release=locked,
            stage=to_state,
            decision=MiniProgramApprovalRecord.Decision.APPROVED,
            note=note,
            actor=actor,
        )
    if to_state == MiniProgramRelease.Status.REWORK:
        MiniProgramApprovalRecord.objects.create(
            release=locked,
            stage=from_state,
            decision=MiniProgramApprovalRecord.Decision.REJECTED,
            note=note,
            actor=actor,
        )
    return locked
