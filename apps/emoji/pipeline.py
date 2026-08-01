from django.db import transaction

from apps.core.models import TransitionEvent

from .models import ApprovalRecord, EmojiPack

ALLOWED_TRANSITIONS = {
    EmojiPack.Status.DRAFT: {
        EmojiPack.Status.BRIEF_APPROVED,
        EmojiPack.Status.ARCHIVED,
    },
    EmojiPack.Status.BRIEF_APPROVED: {
        EmojiPack.Status.GENERATING,
        EmojiPack.Status.REWORK,
    },
    EmojiPack.Status.GENERATING: {
        EmojiPack.Status.CREATIVE_REVIEW,
        EmojiPack.Status.REWORK,
    },
    EmojiPack.Status.CREATIVE_REVIEW: {
        EmojiPack.Status.PROCESSING,
        EmojiPack.Status.REWORK,
    },
    EmojiPack.Status.PROCESSING: {
        EmojiPack.Status.QA_REVIEW,
        EmojiPack.Status.REWORK,
    },
    EmojiPack.Status.QA_REVIEW: {
        EmojiPack.Status.EXPORT_READY,
        EmojiPack.Status.REWORK,
    },
    EmojiPack.Status.EXPORT_READY: {
        EmojiPack.Status.SUBMITTED,
        EmojiPack.Status.REWORK,
    },
    EmojiPack.Status.SUBMITTED: {
        EmojiPack.Status.PUBLISHED,
        EmojiPack.Status.REWORK,
    },
    EmojiPack.Status.REWORK: {
        EmojiPack.Status.GENERATING,
        EmojiPack.Status.PROCESSING,
        EmojiPack.Status.QA_REVIEW,
        EmojiPack.Status.ARCHIVED,
    },
    EmojiPack.Status.PUBLISHED: {EmojiPack.Status.ARCHIVED},
    EmojiPack.Status.ARCHIVED: set(),
}


@transaction.atomic
def transition_pack(pack: EmojiPack, to_state: str, *, actor=None, note: str = ""):
    locked = EmojiPack.objects.select_for_update().get(pk=pack.pk)
    if to_state == locked.status:
        return locked
    if to_state not in ALLOWED_TRANSITIONS.get(locked.status, set()):
        raise ValueError(f"不允许从“{locked.get_status_display()}”进入目标状态。")
    from_state = locked.status
    locked.status = to_state
    locked.save(update_fields=["status", "updated_at"])
    TransitionEvent.objects.create(
        object_type="emoji_pack",
        object_id=locked.pk,
        from_state=from_state,
        to_state=to_state,
        action="transition",
        note=note,
        actor=actor,
    )
    if to_state in {EmojiPack.Status.BRIEF_APPROVED, EmojiPack.Status.EXPORT_READY}:
        ApprovalRecord.objects.create(
            pack=locked,
            stage=to_state,
            decision=ApprovalRecord.Decision.APPROVED,
            note=note,
            actor=actor,
        )
    if to_state == EmojiPack.Status.REWORK:
        ApprovalRecord.objects.create(
            pack=locked,
            stage=from_state,
            decision=ApprovalRecord.Decision.REJECTED,
            note=note,
            actor=actor,
        )
    return locked
