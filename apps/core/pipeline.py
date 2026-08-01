from django.db import transaction

from .models import CreativeProject, TransitionEvent

ALLOWED_PROJECT_TRANSITIONS = {
    CreativeProject.Status.ACTIVE: {
        CreativeProject.Status.PAUSED,
        CreativeProject.Status.COMPLETED,
        CreativeProject.Status.ARCHIVED,
    },
    CreativeProject.Status.PAUSED: {
        CreativeProject.Status.ACTIVE,
        CreativeProject.Status.ARCHIVED,
    },
    CreativeProject.Status.COMPLETED: {CreativeProject.Status.ARCHIVED},
    CreativeProject.Status.ARCHIVED: set(),
}


@transaction.atomic
def transition_project(
    project: CreativeProject,
    to_state: str,
    *,
    actor=None,
    note: str = "",
    action: str = "transition",
    payload: dict | None = None,
):
    locked = CreativeProject.objects.select_for_update().get(pk=project.pk)
    if locked.status == to_state:
        return locked
    if to_state not in ALLOWED_PROJECT_TRANSITIONS.get(locked.status, set()):
        raise ValueError(
            f"不允许从“{locked.get_status_display()}”进入目标项目状态。"
        )
    from_state = locked.status
    locked.status = to_state
    locked.save(update_fields=["status", "updated_at"])
    TransitionEvent.objects.create(
        object_type="creative_project",
        object_id=locked.pk,
        from_state=from_state,
        to_state=to_state,
        action=action,
        note=note,
        actor=actor,
        payload=payload or {},
    )
    return locked
