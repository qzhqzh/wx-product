from dataclasses import dataclass

from .models import MiniProgramRelease
from .services import build_export_bundle, validate_release


@dataclass(frozen=True)
class MiniProgramProductLineAdapter:
    code: str = "mini-program"
    name: str = "小程序"

    stages = tuple(value for value, _label in MiniProgramRelease.Status.choices)

    @staticmethod
    def validate(product, *, actor=None):
        return validate_release(product, actor=actor)

    @staticmethod
    def export(product, *, actor=None):
        return build_export_bundle(product, actor=actor)
