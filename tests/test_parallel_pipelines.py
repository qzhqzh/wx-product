import io
import json
import zipfile

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.miniprogram.models import MiniProgramRelease
from apps.miniprogram.services import (
    build_export_bundle as build_mini_program_export,
)
from apps.miniprogram.services import generate_demo_release, validate_release
from apps.redpacket.models import RedPacketCampaign
from apps.redpacket.services import (
    approve_selected_design,
    build_export_bundle,
    generate_demo_designs,
    select_design,
    validate_campaign,
)


@pytest.mark.django_db(transaction=True)
def test_red_packet_cover_runs_through_design_qa_and_export(
    red_packet_campaign, admin_user
):
    designs = generate_demo_designs(red_packet_campaign, actor=admin_user)
    red_packet_campaign.refresh_from_db()

    assert len(designs) == 3
    assert red_packet_campaign.status == RedPacketCampaign.Status.CREATIVE_REVIEW
    assert all(
        [design.asset.width, design.asset.height] == [957, 1278]
        for design in designs
    )

    select_design(designs[1], actor=admin_user)
    approve_selected_design(
        red_packet_campaign, actor=admin_user, note="角色一致，移动端主体清楚"
    )
    validation = validate_campaign(red_packet_campaign, actor=admin_user)

    assert validation.passed is True
    assert validation.error_count == 0
    assert validation.warning_count == 1

    bundle = build_export_bundle(red_packet_campaign, actor=admin_user)
    red_packet_campaign.refresh_from_db()
    assert red_packet_campaign.status == RedPacketCampaign.Status.EXPORT_READY
    assert bundle.ruleset.version == "2026-07-seed"

    with bundle.file.file.open("rb") as source:
        with zipfile.ZipFile(io.BytesIO(source.read())) as archive:
            names = set(archive.namelist())
            assert "manifest.json" in names
            assert "cover/cover.png" in names
            assert "support/preview.png" in names
            assert "rights/README.txt" in names
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["schema"] == "wx-product.red-packet-cover.export.v1"
            assert manifest["ruleset"]["version"] == "2026-07-seed"


@pytest.mark.django_db(transaction=True)
def test_red_packet_submission_order_and_distribution_complete_inventory(
    red_packet_campaign, admin_user
):
    designs = generate_demo_designs(red_packet_campaign, actor=admin_user)
    select_design(designs[0], actor=admin_user)
    approve_selected_design(red_packet_campaign, actor=admin_user)
    build_export_bundle(red_packet_campaign, actor=admin_user)
    client = APIClient()
    client.force_login(admin_user)

    response = client.post(
        reverse(
            "api-red-packet-submission",
            kwargs={"campaign_id": red_packet_campaign.pk},
        ),
        {"platform_work_id": "RP-2026-001"},
        format="json",
    )
    assert response.status_code == 201
    submission_id = response.json()["id"]

    response = client.patch(
        reverse(
            "api-red-packet-submission",
            kwargs={"campaign_id": red_packet_campaign.pk},
        ),
        {"id": submission_id, "status": "approved"},
        format="json",
    )
    assert response.status_code == 200
    red_packet_campaign.refresh_from_db()
    assert red_packet_campaign.status == RedPacketCampaign.Status.APPROVED

    response = client.post(
        reverse(
            "api-red-packet-order",
            kwargs={"campaign_id": red_packet_campaign.pk},
        ),
        {"platform_order_no": "ORDER-001", "quantity": 20, "unit_cost": "1.50"},
        format="json",
    )
    assert response.status_code == 201
    order_id = response.json()["id"]

    response = client.post(
        reverse(
            "api-red-packet-distribution",
            kwargs={
                "campaign_id": red_packet_campaign.pk,
                "order_id": order_id,
            },
        ),
        {"channel": "内部社群", "quantity": 20},
        format="json",
    )
    assert response.status_code == 201
    assert response.json()["available_quantity"] == 0
    red_packet_campaign.refresh_from_db()
    assert red_packet_campaign.status == RedPacketCampaign.Status.COMPLETED


@pytest.mark.django_db(transaction=True)
def test_mini_program_runs_through_build_tests_qa_and_export(
    mini_program_release, admin_user
):
    generate_demo_release(mini_program_release, actor=admin_user)
    mini_program_release.refresh_from_db()

    assert mini_program_release.status == MiniProgramRelease.Status.COMPLIANCE_REVIEW
    assert mini_program_release.artifacts.filter(is_current=True).count() == 4
    assert mini_program_release.checklist_items.filter(is_completed=True).count() == 6
    assert mini_program_release.test_cases.filter(result="passed").count() == 3

    validation = validate_release(mini_program_release, actor=admin_user)
    assert validation.passed is True
    assert validation.error_count == 0
    assert validation.warning_count == 0

    bundle = build_mini_program_export(mini_program_release, actor=admin_user)
    mini_program_release.refresh_from_db()
    assert mini_program_release.status == MiniProgramRelease.Status.EXPORT_READY
    assert bundle.ruleset.version == "2026-07-seed"

    with bundle.file.file.open("rb") as source:
        with zipfile.ZipFile(io.BytesIO(source.read())) as archive:
            names = set(archive.namelist())
            assert "manifest.json" in names
            assert "qa/checklist.json" in names
            assert "qa/test-report.json" in names
            assert "compliance/privacy-summary.txt" in names
            assert any(name.startswith("build/") for name in names)
            assert len([name for name in names if name.startswith("screenshots/")]) == 2
            manifest = json.loads(archive.read("manifest.json"))
            assert manifest["schema"] == "wx-product.mini-program.release.v1"
            assert len(manifest["test_cases"]) == 3


@pytest.mark.django_db(transaction=True)
def test_mini_program_submission_can_reach_released(
    mini_program_release, admin_user
):
    generate_demo_release(mini_program_release, actor=admin_user)
    build_mini_program_export(mini_program_release, actor=admin_user)
    client = APIClient()
    client.force_login(admin_user)
    endpoint = reverse(
        "api-mini-program-submission",
        kwargs={"release_id": mini_program_release.pk},
    )

    response = client.post(
        endpoint,
        {"platform_audit_id": "AUDIT-001"},
        format="json",
    )
    assert response.status_code == 201
    submission_id = response.json()["id"]

    response = client.patch(
        endpoint,
        {"id": submission_id, "status": "approved"},
        format="json",
    )
    assert response.status_code == 200

    response = client.patch(
        endpoint,
        {"id": submission_id, "status": "released"},
        format="json",
    )
    assert response.status_code == 200
    mini_program_release.refresh_from_db()
    assert mini_program_release.status == MiniProgramRelease.Status.RELEASED


@pytest.mark.django_db
def test_parallel_pipeline_pages_replace_placeholders(
    admin_user, red_packet_campaign, mini_program_release
):
    client = APIClient()
    client.force_login(admin_user)

    red_response = client.get(reverse("red-packet-list"))
    mini_response = client.get(reverse("mini-program-list"))
    red_workbench_response = client.get(
        reverse(
            "red-packet-workbench",
            kwargs={"campaign_id": red_packet_campaign.pk},
        )
    )
    mini_workbench_response = client.get(
        reverse(
            "mini-program-workbench",
            kwargs={"release_id": mini_program_release.pk},
        )
    )

    assert red_response.status_code == 200
    assert "红包封面流水线" in red_response.content.decode()
    assert mini_response.status_code == 200
    assert "小程序发布流水线" in mini_response.content.decode()
    assert red_workbench_response.status_code == 200
    assert 'id="red-packet-workbench"' in red_workbench_response.content.decode()
    assert "/static/dist/assets/main-" in red_workbench_response.content.decode()
    assert mini_workbench_response.status_code == 200
    assert 'id="mini-program-workbench"' in mini_workbench_response.content.decode()
    assert "/static/dist/assets/main-" in mini_workbench_response.content.decode()
