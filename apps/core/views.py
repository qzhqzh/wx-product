from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.emoji.models import EmojiPack, GenerationJob
from apps.emoji.prompts import attach_default_presets
from apps.miniprogram.models import MiniProgramRelease
from apps.redpacket.models import RedPacketCampaign

from .forms import CreativeProjectForm, EmojiPackForm
from .models import CreativeProject, ProductLine, TransitionEvent


def health(request):
    return JsonResponse({"ok": True, "service": "wx-pipeline"})


@login_required
def dashboard(request):
    projects = list(
        CreativeProject.objects.select_related("product_line", "owner")
        .annotate(
            pack_count=Count("emoji_packs", distinct=True),
            active_pack_count=Count(
                "emoji_packs",
                filter=~Q(
                    emoji_packs__status__in=[
                        EmojiPack.Status.PUBLISHED,
                        EmojiPack.Status.ARCHIVED,
                    ]
                ),
                distinct=True,
            ),
            campaign_count=Count("red_packet_campaigns", distinct=True),
            active_campaign_count=Count(
                "red_packet_campaigns",
                filter=~Q(
                    red_packet_campaigns__status__in=[
                        RedPacketCampaign.Status.COMPLETED,
                        RedPacketCampaign.Status.ARCHIVED,
                    ]
                ),
                distinct=True,
            ),
            release_count=Count("mini_program_releases", distinct=True),
            active_release_count=Count(
                "mini_program_releases",
                filter=~Q(
                    mini_program_releases__status__in=[
                        MiniProgramRelease.Status.RELEASED,
                        MiniProgramRelease.Status.ARCHIVED,
                    ]
                ),
                distinct=True,
            ),
        )
        .order_by("-updated_at")[:8]
    )
    for project in projects:
        project.output_count = (
            project.pack_count + project.campaign_count + project.release_count
        )
        project.active_output_count = (
            project.active_pack_count
            + project.active_campaign_count
            + project.active_release_count
        )
    packs = EmojiPack.objects.select_related("project", "owner").order_by("-updated_at")
    campaigns = RedPacketCampaign.objects.select_related("project", "owner").order_by(
        "-updated_at"
    )
    releases = MiniProgramRelease.objects.select_related("project", "owner").order_by(
        "-updated_at"
    )
    jobs = GenerationJob.objects.select_related("pack", "item").order_by("-created_at")[:8]
    stats = {
        "active_projects": CreativeProject.objects.filter(
            status=CreativeProject.Status.ACTIVE
        ).count(),
        "in_production": (
            packs.exclude(
                status__in=[EmojiPack.Status.PUBLISHED, EmojiPack.Status.ARCHIVED]
            ).count()
            + campaigns.exclude(
                status__in=[
                    RedPacketCampaign.Status.COMPLETED,
                    RedPacketCampaign.Status.ARCHIVED,
                ]
            ).count()
            + releases.exclude(
                status__in=[
                    MiniProgramRelease.Status.RELEASED,
                    MiniProgramRelease.Status.ARCHIVED,
                ]
            ).count()
        ),
        "needs_attention": (
            packs.filter(
                status__in=[EmojiPack.Status.REWORK, EmojiPack.Status.QA_REVIEW]
            ).count()
            + campaigns.filter(
                status__in=[
                    RedPacketCampaign.Status.REWORK,
                    RedPacketCampaign.Status.QA_REVIEW,
                ]
            ).count()
            + releases.filter(
                status__in=[
                    MiniProgramRelease.Status.REWORK,
                    MiniProgramRelease.Status.QA_REVIEW,
                ]
            ).count()
        ),
        "published": (
            packs.filter(status=EmojiPack.Status.PUBLISHED).count()
            + campaigns.filter(status=RedPacketCampaign.Status.COMPLETED).count()
            + releases.filter(status=MiniProgramRelease.Status.RELEASED).count()
        ),
    }
    return render(
        request,
        "core/dashboard.html",
        {
            "projects": projects,
            "packs": packs[:8],
            "campaigns": campaigns[:5],
            "releases": releases[:5],
            "jobs": jobs,
            "stats": stats,
        },
    )


@login_required
def project_list(request):
    projects = CreativeProject.objects.select_related(
        "product_line", "owner", "character_version__character", "trend_topic"
    )
    return render(
        request,
        "core/project_list.html",
        {"projects": projects, "form": CreativeProjectForm()},
    )


@login_required
def project_create(request):
    if request.method != "POST":
        return redirect("project-list")
    form = CreativeProjectForm(request.POST)
    if form.is_valid():
        project = form.save(commit=False)
        project.product_line = ProductLine.objects.get(code="emoji")
        project.owner = request.user
        project.full_clean()
        project.save()
        messages.success(request, "项目已创建，可以开始建立表情专辑。")
        return redirect("project-detail", project_id=project.pk)
    projects = CreativeProject.objects.select_related("product_line", "owner")
    return render(
        request,
        "core/project_list.html",
        {"projects": projects, "form": form},
        status=422,
    )


@login_required
def project_detail(request, project_id):
    project = get_object_or_404(
        CreativeProject.objects.select_related(
            "product_line",
            "owner",
            "character_version__character",
            "trend_topic",
        ),
        pk=project_id,
    )
    if project.product_line.code == "red-packet-cover":
        campaign = project.red_packet_campaigns.first()
        return (
            redirect("red-packet-workbench", campaign_id=campaign.pk)
            if campaign
            else redirect("red-packet-list")
        )
    if project.product_line.code == "mini-program":
        release = project.mini_program_releases.first()
        return (
            redirect("mini-program-workbench", release_id=release.pk)
            if release
            else redirect("mini-program-list")
        )
    packs = project.emoji_packs.prefetch_related("items").select_related("owner", "ruleset")
    events = TransitionEvent.objects.filter(
        object_type="emoji_pack", object_id__in=packs.values_list("id", flat=True)
    )[:20]
    return render(
        request,
        "core/project_detail.html",
        {
            "project": project,
            "packs": packs,
            "events": events,
            "pack_form": EmojiPackForm(),
        },
    )


@login_required
def pack_create(request, project_id):
    project = get_object_or_404(CreativeProject, pk=project_id)
    if request.method != "POST":
        return redirect("project-detail", project_id=project.pk)
    form = EmojiPackForm(request.POST)
    if form.is_valid():
        pack = form.save(commit=False)
        pack.project = project
        pack.owner = request.user
        pack.save()
        attach_default_presets(pack)
        messages.success(request, "专辑已创建，先确认 Brief 再生成语义矩阵。")
        return redirect("pack-workbench", pack_id=pack.pk)
    messages.error(request, "专辑信息有误，请检查后重试。")
    packs = project.emoji_packs.all()
    return render(
        request,
        "core/project_detail.html",
        {"project": project, "packs": packs, "pack_form": form, "events": []},
        status=422,
    )


@login_required
def pack_workbench(request, pack_id):
    pack = get_object_or_404(
        EmojiPack.objects.select_related(
            "project__character_version__character",
            "project__trend_topic",
            "ruleset",
            "cover_asset",
            "icon_asset",
            "banner_asset",
        ),
        pk=pack_id,
    )
    return render(request, "core/pack_workbench.html", {"pack": pack})


@login_required
def product_placeholder(request, code):
    line = get_object_or_404(ProductLine, code=code)
    if line.status == ProductLine.Status.ACTIVE and code == "emoji":
        return redirect("emoji-pack-list")
    return render(request, "core/product_placeholder.html", {"line": line})


@login_required
def download_export(request, export_id):
    from apps.emoji.models import ExportBundle

    bundle = get_object_or_404(ExportBundle.objects.select_related("file"), pk=export_id)
    response = HttpResponse(
        bundle.file.file.open("rb"), content_type="application/zip"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="emoji-export-{bundle.pack_id}.zip"'
    )
    return response


@login_required
def view_asset(request, asset_id):
    from apps.assets.models import AssetVersion

    asset = get_object_or_404(AssetVersion, pk=asset_id)
    response = HttpResponse(
        asset.file.open("rb"), content_type=asset.mime_type or "application/octet-stream"
    )
    response["Content-Disposition"] = f'inline; filename="{asset.original_name}"'
    response["Cache-Control"] = "private, max-age=300"
    response["X-Content-Type-Options"] = "nosniff"
    return response
