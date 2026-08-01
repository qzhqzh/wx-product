import hashlib
import json
from collections.abc import Iterable

from django.db import models

SNAPSHOT_SCHEMA = 1
EXCLUDED_FIELDS = {"created_at", "updated_at", "status"}


def _model_payload(instance: models.Model, *, exclude: set[str] | None = None) -> dict:
    excluded = EXCLUDED_FIELDS | (exclude or set())
    payload = {}
    for field in instance._meta.concrete_fields:
        if field.name in excluded:
            continue
        payload[field.name] = getattr(instance, field.attname)
    return payload


def _asset_payload(asset) -> dict | None:
    if asset is None:
        return None
    return {
        "id": asset.pk,
        "checksum_sha256": asset.checksum_sha256,
        "size_bytes": asset.size_bytes,
        "kind": asset.kind,
        "metadata": asset.metadata,
    }


def _rows(items: Iterable[models.Model], *, asset_field: str | None = None) -> list[dict]:
    rows = []
    for item in items:
        row = _model_payload(item)
        if asset_field:
            row["asset_snapshot"] = _asset_payload(getattr(item, asset_field, None))
        rows.append(row)
    return rows


def _rights_payload(project) -> list[dict]:
    evidence = project.rights_evidence.select_related("asset").order_by("pk")
    return _rows(evidence, asset_field="asset")


def _ruleset_payload(ruleset) -> dict | None:
    if ruleset is None:
        return None
    return _model_payload(ruleset, exclude={"created_at"})


def emoji_payload(pack) -> dict:
    pack = type(pack).objects.select_related(
        "project", "ruleset", "cover_asset", "icon_asset", "banner_asset"
    ).get(pk=pack.pk)
    items = pack.items.select_related("selected_asset").order_by("order", "pk")
    presets = pack.prompt_presets.order_by("category", "name", "pk")
    return {
        "kind": "emoji",
        "pack": _model_payload(pack),
        "ruleset": _ruleset_payload(pack.ruleset),
        "items": _rows(items, asset_field="selected_asset"),
        "prompt_presets": _rows(presets),
        "support_assets": {
            "cover": _asset_payload(pack.cover_asset),
            "icon": _asset_payload(pack.icon_asset),
            "banner": _asset_payload(pack.banner_asset),
        },
        "rights": _rights_payload(pack.project),
    }


def red_packet_payload(campaign) -> dict:
    campaign = type(campaign).objects.select_related(
        "project", "ruleset", "preview_asset"
    ).get(pk=campaign.pk)
    designs = campaign.designs.select_related("asset").order_by("order", "pk")
    return {
        "kind": "red_packet",
        "campaign": _model_payload(campaign),
        "ruleset": _ruleset_payload(campaign.ruleset),
        "designs": _rows(designs, asset_field="asset"),
        "preview_asset": _asset_payload(campaign.preview_asset),
        "rights": _rights_payload(campaign.project),
    }


def mini_program_payload(release) -> dict:
    release = type(release).objects.select_related("project", "ruleset").get(pk=release.pk)
    artifacts = release.artifacts.select_related("asset").order_by(
        "artifact_type", "created_at", "pk"
    )
    checklist = release.checklist_items.order_by("category", "title", "pk")
    test_cases = release.test_cases.order_by("name", "pk")
    return {
        "kind": "mini_program",
        "release": _model_payload(release),
        "ruleset": _ruleset_payload(release.ruleset),
        "artifacts": _rows(artifacts, asset_field="asset"),
        "checklist": _rows(checklist),
        "test_cases": _rows(test_cases),
        "rights": _rights_payload(release.project),
    }


def _digest(payload: dict) -> str:
    serialized = json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(serialized).hexdigest()


def fingerprint_for_export(export) -> str:
    model_name = export._meta.model_name
    if model_name == "exportbundle":
        return _digest(emoji_payload(export.pack))
    if model_name == "redpacketexportbundle":
        return _digest(red_packet_payload(export.campaign))
    if model_name == "miniprogramexportbundle":
        return _digest(mini_program_payload(export.release))
    raise TypeError(f"Unsupported export model: {export._meta.label}")


def stamp_export(export) -> str:
    fingerprint = fingerprint_for_export(export)
    manifest = dict(export.manifest or {})
    manifest["integrity"] = {
        "schema_version": SNAPSHOT_SCHEMA,
        "input_fingerprint": fingerprint,
    }
    type(export).objects.filter(pk=export.pk).update(manifest=manifest)
    export.manifest = manifest
    return fingerprint


def export_is_current(export) -> bool:
    integrity = (export.manifest or {}).get("integrity", {})
    recorded = integrity.get("input_fingerprint")
    return bool(recorded) and recorded == fingerprint_for_export(export)
