from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import CreativeProject, ProductLine

from .forms import RedPacketCampaignForm
from .models import RedPacketCampaign, RedPacketExportBundle


@login_required
def campaign_list(request):
    campaigns = RedPacketCampaign.objects.select_related("project", "owner")
    return render(
        request,
        "redpacket/campaign_list.html",
        {"campaigns": campaigns, "form": RedPacketCampaignForm()},
    )


@login_required
@transaction.atomic
def campaign_create(request):
    if request.method != "POST":
        return redirect("red-packet-list")
    form = RedPacketCampaignForm(request.POST)
    if form.is_valid():
        line = ProductLine.objects.get(code="red-packet-cover")
        project = CreativeProject.objects.create(
            title=form.cleaned_data["name"],
            product_line=line,
            lane=CreativeProject.Lane.PRODUCT,
            description=form.cleaned_data["description"],
            owner=request.user,
        )
        campaign = form.save(commit=False)
        campaign.project = project
        campaign.owner = request.user
        campaign.save()
        messages.success(request, "红包封面项目已创建，可以开始生成设计候选。")
        return redirect("red-packet-workbench", campaign_id=campaign.pk)
    campaigns = RedPacketCampaign.objects.select_related("project", "owner")
    return render(
        request,
        "redpacket/campaign_list.html",
        {"campaigns": campaigns, "form": form},
        status=422,
    )


@login_required
def campaign_workbench(request, campaign_id):
    campaign = get_object_or_404(
        RedPacketCampaign.objects.select_related("project", "ruleset"),
        pk=campaign_id,
    )
    return render(
        request,
        "redpacket/campaign_workbench.html",
        {"campaign": campaign},
    )


@login_required
def download_export(request, export_id):
    bundle = get_object_or_404(
        RedPacketExportBundle.objects.select_related("file"), pk=export_id
    )
    response = HttpResponse(
        bundle.file.file.open("rb"), content_type="application/zip"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="red-packet-{bundle.campaign_id}.zip"'
    )
    return response
