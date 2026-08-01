from django import forms

from .models import MiniProgramRelease


class MiniProgramReleaseForm(forms.ModelForm):
    class Meta:
        model = MiniProgramRelease
        fields = (
            "name",
            "app_id",
            "version",
            "release_type",
            "service_category",
            "prd_summary",
            "change_log",
            "privacy_summary",
        )
        widgets = {
            "prd_summary": forms.Textarea(attrs={"rows": 4}),
            "change_log": forms.Textarea(attrs={"rows": 3}),
            "privacy_summary": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
