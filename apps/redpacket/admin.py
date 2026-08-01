from django.contrib import admin

from .models import (
    RedPacketCampaign,
    RedPacketDesign,
    RedPacketDistribution,
    RedPacketExportBundle,
    RedPacketOrder,
    RedPacketSubmission,
    RedPacketValidationRun,
)

admin.site.register(RedPacketCampaign)
admin.site.register(RedPacketDesign)
admin.site.register(RedPacketValidationRun)
admin.site.register(RedPacketExportBundle)
admin.site.register(RedPacketSubmission)
admin.site.register(RedPacketOrder)
admin.site.register(RedPacketDistribution)
