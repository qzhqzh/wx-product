from django import forms

from apps.emoji.models import EmojiPack

from .models import CreativeProject, IPCharacterVersion, TrendTopic


class CreativeProjectForm(forms.ModelForm):
    class Meta:
        model = CreativeProject
        fields = (
            "title",
            "lane",
            "description",
            "character_version",
            "trend_topic",
            "due_at",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 3}),
            "due_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["character_version"].queryset = IPCharacterVersion.objects.select_related(
            "character"
        ).order_by("character__name", "-version")
        self.fields["trend_topic"].queryset = TrendTopic.objects.order_by("-observed_at")
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")


class EmojiPackForm(forms.ModelForm):
    class Meta:
        model = EmojiPack
        fields = (
            "name",
            "pack_type",
            "media_type",
            "target_count",
            "audience",
            "tone",
            "creative_brief",
            "negative_prompt",
        )
        labels = {
            "name": "专辑名称",
            "pack_type": "专辑类型",
            "media_type": "媒介类型",
            "target_count": "目标数量",
            "audience": "目标受众",
            "tone": "整体语气",
            "creative_brief": "创意 Brief",
            "negative_prompt": "专辑负向要求",
        }
        widgets = {
            "creative_brief": forms.Textarea(attrs={"rows": 4}),
            "negative_prompt": forms.Textarea(attrs={"rows": 2}),
        }

    def clean_target_count(self):
        count = self.cleaned_data["target_count"]
        pack_type = self.cleaned_data.get("pack_type")
        allowed = {1} if pack_type == EmojiPack.PackType.SINGLE else {8, 16, 24}
        if count not in allowed:
            raise forms.ValidationError(f"当前规则允许的数量为：{sorted(allowed)}")
        return count

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
