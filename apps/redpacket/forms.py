from django import forms

from .models import RedPacketCampaign


class RedPacketCampaignForm(forms.ModelForm):
    class Meta:
        model = RedPacketCampaign
        fields = (
            "name",
            "description",
            "audience",
            "cover_story",
            "greeting",
            "design_target",
            "planned_quantity",
        )
        widgets = {
            "description": forms.Textarea(attrs={"rows": 2}),
            "cover_story": forms.Textarea(attrs={"rows": 4}),
        }

    def clean_design_target(self):
        value = self.cleaned_data["design_target"]
        if value < 1 or value > 6:
            raise forms.ValidationError("候选方案数量应在 1–6 之间。")
        return value

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")
