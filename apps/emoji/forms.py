from django import forms

from apps.core.forms import EmojiPackForm
from apps.core.models import CreativeProject

from .models import PromptPreset


class StandaloneEmojiPackForm(EmojiPackForm):
    project = forms.ModelChoiceField(
        label="所属项目",
        queryset=CreativeProject.objects.none(),
        empty_label="选择一个表情项目",
    )

    class Meta(EmojiPackForm.Meta):
        fields = ("project", *EmojiPackForm.Meta.fields)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["project"].queryset = CreativeProject.objects.filter(
            product_line__code="emoji"
        ).order_by("-updated_at")


class PromptPresetForm(forms.ModelForm):
    class Meta:
        model = PromptPreset
        fields = (
            "name",
            "category",
            "description",
            "content",
            "is_default",
            "is_active",
        )
        labels = {
            "name": "名称",
            "category": "分类",
            "description": "使用说明",
            "content": "提示词内容",
            "is_default": "设为该分类默认项",
            "is_active": "启用",
        }
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "content": forms.Textarea(attrs={"rows": 6}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            css_class = (
                "form-checkbox"
                if isinstance(field.widget, forms.CheckboxInput)
                else "form-control"
            )
            field.widget.attrs.setdefault("class", css_class)
