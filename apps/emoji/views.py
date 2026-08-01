from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.models import CreativeProject

from .forms import PromptPresetForm, StandaloneEmojiPackForm
from .models import EmojiPack, PromptPreset
from .prompts import attach_default_presets


@login_required
def pack_list(request):
    packs = EmojiPack.objects.select_related("project", "owner").prefetch_related(
        "prompt_presets"
    )
    return render(
        request,
        "emoji/pack_list.html",
        {
            "packs": packs,
            "form": StandaloneEmojiPackForm(),
            "has_projects": CreativeProject.objects.filter(
                product_line__code="emoji"
            ).exists(),
        },
    )


@login_required
def pack_create(request):
    if request.method != "POST":
        return redirect("emoji-pack-list")
    form = StandaloneEmojiPackForm(request.POST)
    if form.is_valid():
        pack = form.save(commit=False)
        pack.owner = request.user
        pack.save()
        attach_default_presets(pack)
        messages.success(request, "表情专辑已创建，并应用了默认提示词方案。")
        return redirect("pack-workbench", pack_id=pack.pk)
    packs = EmojiPack.objects.select_related("project", "owner").prefetch_related(
        "prompt_presets"
    )
    return render(
        request,
        "emoji/pack_list.html",
        {
            "packs": packs,
            "form": form,
            "has_projects": CreativeProject.objects.filter(
                product_line__code="emoji"
            ).exists(),
        },
        status=422,
    )


@login_required
def prompt_library(request):
    edit_preset = None
    edit_id = request.GET.get("edit")
    if edit_id:
        edit_preset = get_object_or_404(PromptPreset, pk=edit_id)
    return render(
        request,
        "emoji/prompt_library.html",
        {
            "presets": PromptPreset.objects.select_related("created_by"),
            "form": PromptPresetForm(instance=edit_preset),
            "edit_preset": edit_preset,
        },
    )


@login_required
def prompt_preset_create(request):
    if request.method != "POST":
        return redirect("emoji-prompt-library")
    return _save_prompt_preset(request)


@login_required
def prompt_preset_update(request, preset_id):
    if request.method != "POST":
        return redirect("emoji-prompt-library")
    preset = get_object_or_404(PromptPreset, pk=preset_id)
    return _save_prompt_preset(request, preset)


def _save_prompt_preset(request, preset=None):
    form = PromptPresetForm(request.POST, instance=preset)
    if form.is_valid():
        with transaction.atomic():
            if form.cleaned_data["is_default"]:
                PromptPreset.objects.filter(
                    category=form.cleaned_data["category"],
                    is_default=True,
                ).exclude(pk=getattr(preset, "pk", None)).update(is_default=False)
            saved = form.save(commit=False)
            if not saved.created_by_id:
                saved.created_by = request.user
            saved.save()
        messages.success(request, f"提示词“{saved.name}”已保存。")
        return redirect("emoji-prompt-library")
    return render(
        request,
        "emoji/prompt_library.html",
        {
            "presets": PromptPreset.objects.select_related("created_by"),
            "form": form,
            "edit_preset": preset,
        },
        status=422,
    )


@login_required
def prompt_preset_toggle(request, preset_id):
    if request.method != "POST":
        return redirect("emoji-prompt-library")
    preset = get_object_or_404(PromptPreset, pk=preset_id)
    preset.is_active = not preset.is_active
    if not preset.is_active:
        preset.is_default = False
    preset.save(update_fields=["is_active", "is_default", "updated_at"])
    state = "启用" if preset.is_active else "停用"
    messages.success(request, f"提示词“{preset.name}”已{state}。")
    return redirect("emoji-prompt-library")
