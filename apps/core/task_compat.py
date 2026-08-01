from types import MethodType

from apps.emoji.models import EmojiPack, GenerationJob
from apps.emoji.pipeline import transition_pack

_INSTALLED = False


def install_plan_task_compatibility() -> None:
    """Preserve direct task invocation while keeping all status changes audited."""
    global _INSTALLED
    if _INSTALLED:
        return

    from apps.emoji.tasks import plan_pack_task

    task = (
        plan_pack_task._get_current_object()
        if hasattr(plan_pack_task, "_get_current_object")
        else plan_pack_task
    )
    original_run = task.run

    def run(self, job_id):
        result = original_run(job_id)
        job = GenerationJob.objects.select_related("pack").filter(pk=job_id).first()
        if job is None or job.status != GenerationJob.Status.SUCCEEDED:
            return result

        pack = job.pack
        if pack.status == EmojiPack.Status.DRAFT:
            pack = transition_pack(
                pack,
                EmojiPack.Status.BRIEF_APPROVED,
                actor=job.created_by,
                note="语义策划任务确认 Brief",
            )
        if pack.status in {EmojiPack.Status.BRIEF_APPROVED, EmojiPack.Status.REWORK}:
            transition_pack(
                pack,
                EmojiPack.Status.GENERATING,
                actor=job.created_by,
                note="语义策划完成，进入素材生成",
            )
        return result

    task.run = MethodType(run, task)
    _INSTALLED = True
