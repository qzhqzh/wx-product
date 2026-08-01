from datetime import timedelta

from django.db import transaction
from django.db.models.signals import post_save, pre_save
from django.dispatch import receiver
from django.utils import timezone

from apps.emoji.models import EmojiPack, ExportBundle
from apps.miniprogram.models import MiniProgramExportBundle, MiniProgramRelease
from apps.redpacket.models import (
    RedPacketCampaign,
    RedPacketDistribution,
    RedPacketExportBundle,
    RedPacketOrder,
)

from .export_integrity import stamp_export
from .models import CreativeProject, TransitionEvent

STATUS_MODELS = {
    EmojiPack: "emoji_pack",
    RedPacketCampaign: "red_packet_campaign",
    MiniProgramRelease: "mini_program_release",
    CreativeProject: "creative_project",
}


@receiver(pre_save)
def remember_previous_status(sender, instance, **kwargs):
    object_type = STATUS_MODELS.get(sender)
    if object_type is None or not instance.pk:
        return
    previous = sender.objects.filter(pk=instance.pk).values_list("status", flat=True).first()
    instance._pipeline_previous_status = previous


@receiver(post_save)
def ensure_status_audit(sender, instance, created, **kwargs):
    object_type = STATUS_MODELS.get(sender)
    previous = getattr(instance, "_pipeline_previous_status", None)
    if object_type is None or created or previous is None or previous == instance.status:
        return

    changed_at = timezone.now()
    object_id = instance.pk
    to_state = instance.status

    def ensure_event():
        recent = TransitionEvent.objects.filter(
            object_type=object_type,
            object_id=object_id,
            from_state=previous,
            to_state=to_state,
            created_at__gte=changed_at - timedelta(seconds=10),
        ).exists()
        if not recent:
            TransitionEvent.objects.create(
                object_type=object_type,
                object_id=object_id,
                from_state=previous,
                to_state=to_state,
                action="implicit_transition",
                note="状态由系统任务或兼容路径更新。",
                payload={"audit_fallback": True},
            )

    transaction.on_commit(ensure_event)


@receiver(post_save, sender=ExportBundle)
@receiver(post_save, sender=RedPacketExportBundle)
@receiver(post_save, sender=MiniProgramExportBundle)
def stamp_export_integrity(sender, instance, created, **kwargs):
    if created or "integrity" not in (instance.manifest or {}):
        stamp_export(instance)


@receiver(post_save, sender=RedPacketDistribution)
def audit_distribution(sender, instance, created, **kwargs):
    if not created:
        return
    order = instance.order
    TransitionEvent.objects.create(
        object_type="red_packet_order",
        object_id=order.pk,
        from_state=order.status,
        to_state=order.status,
        action="distribution",
        note=f"通过{instance.channel}发放 {instance.quantity} 份红包封面",
        actor=instance.created_by,
        payload={
            "distribution_id": str(instance.pk),
            "campaign_id": str(order.campaign_id),
            "quantity": instance.quantity,
        },
    )

    campaign_id = order.campaign_id

    def complete_campaign_if_ready():
        from apps.redpacket.pipeline import transition_campaign

        campaign = RedPacketCampaign.objects.filter(pk=campaign_id).first()
        if campaign is None or campaign.status != RedPacketCampaign.Status.DISTRIBUTING:
            return
        unfinished = campaign.orders.exclude(
            status__in=[
                RedPacketOrder.Status.EXHAUSTED,
                RedPacketOrder.Status.CANCELLED,
            ]
        ).exists()
        has_distributed_order = campaign.orders.filter(
            status=RedPacketOrder.Status.EXHAUSTED
        ).exists()
        if not unfinished and has_distributed_order:
            transition_campaign(
                campaign,
                RedPacketCampaign.Status.COMPLETED,
                note="全部有效红包封面库存已发放",
            )

    transaction.on_commit(complete_campaign_if_ready)
