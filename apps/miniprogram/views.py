from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import CreativeProject, ProductLine

from .forms import MiniProgramReleaseForm
from .models import MiniProgramExportBundle, MiniProgramRelease
from .services import ensure_default_checklist, ensure_default_tests


@login_required
def release_list(request):
    releases = MiniProgramRelease.objects.select_related("project", "owner")
    return render(
        request,
        "miniprogram/release_list.html",
        {"releases": releases, "form": MiniProgramReleaseForm()},
    )


@login_required
@transaction.atomic
def release_create(request):
    if request.method != "POST":
        return redirect("mini-program-list")
    form = MiniProgramReleaseForm(request.POST)
    if form.is_valid():
        line = ProductLine.objects.get(code="mini-program")
        project = CreativeProject.objects.create(
            title=form.cleaned_data["name"],
            product_line=line,
            lane=CreativeProject.Lane.PRODUCT,
            description=form.cleaned_data["prd_summary"],
            owner=request.user,
        )
        release = form.save(commit=False)
        release.project = project
        release.owner = request.user
        release.save()
        ensure_default_checklist(release)
        ensure_default_tests(release)
        messages.success(request, "小程序版本已创建，可以开始准备构建和体验版。")
        return redirect("mini-program-workbench", release_id=release.pk)
    releases = MiniProgramRelease.objects.select_related("project", "owner")
    return render(
        request,
        "miniprogram/release_list.html",
        {"releases": releases, "form": form},
        status=422,
    )


@login_required
def release_workbench(request, release_id):
    release = get_object_or_404(
        MiniProgramRelease.objects.select_related("project", "ruleset"),
        pk=release_id,
    )
    return render(
        request,
        "miniprogram/release_workbench.html",
        {"release": release},
    )


@login_required
def download_export(request, export_id):
    bundle = get_object_or_404(
        MiniProgramExportBundle.objects.select_related("file"), pk=export_id
    )
    response = HttpResponse(
        bundle.file.file.open("rb"), content_type="application/zip"
    )
    response["Content-Disposition"] = (
        f'attachment; filename="mini-program-{bundle.release.version}.zip"'
    )
    return response
