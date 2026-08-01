from dataclasses import dataclass

from .models import RedPacketCampaign
from .services import build_export_bundle, validate_campaign


@dataclass(frozen=True)
class RedPacketProductLineAdapter:
    code: str = "red-packet-cover"
    name: str = "红包封面"

    stages = tuple(value for value, _label in RedPacketCampaign.Status.choices)

    @staticmethod
    def validate(product, *, actor=None):
        return validate_campaign(product, actor=actor)

    @staticmethod
    def export(product, *, actor=None):
        return build_export_bundle(product, actor=actor)
