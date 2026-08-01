from dataclasses import dataclass

from .models import EmojiPack
from .services import build_export_bundle, validate_pack


@dataclass(frozen=True)
class EmojiProductLineAdapter:
    code: str = "emoji"
    name: str = "表情包"

    stages = tuple(value for value, _label in EmojiPack.Status.choices)

    @staticmethod
    def validate(product, *, actor=None):
        return validate_pack(product, actor=actor)

    @staticmethod
    def export(product, *, actor=None):
        return build_export_bundle(product, actor=actor)
