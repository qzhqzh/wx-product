from django.urls import reverse
from rest_framework import serializers

from .models import AssetVersion


class AssetSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = AssetVersion
        fields = (
            "id",
            "original_name",
            "kind",
            "source",
            "mime_type",
            "size_bytes",
            "width",
            "height",
            "frame_count",
            "duration_ms",
            "checksum_sha256",
            "url",
            "created_at",
        )

    def get_url(self, obj):
        return reverse("view-asset", kwargs={"asset_id": obj.pk})
