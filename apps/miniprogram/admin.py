from django.contrib import admin

from .models import (
    MiniProgramArtifact,
    MiniProgramChecklistItem,
    MiniProgramExportBundle,
    MiniProgramRelease,
    MiniProgramSubmission,
    MiniProgramTestCase,
    MiniProgramValidationRun,
)

admin.site.register(MiniProgramRelease)
admin.site.register(MiniProgramArtifact)
admin.site.register(MiniProgramChecklistItem)
admin.site.register(MiniProgramTestCase)
admin.site.register(MiniProgramValidationRun)
admin.site.register(MiniProgramExportBundle)
admin.site.register(MiniProgramSubmission)
