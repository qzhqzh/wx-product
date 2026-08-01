from django.urls import path

from .api import (
    ArtifactUploadApi,
    ChecklistApi,
    ExportReleaseApi,
    PrepareDemoReleaseApi,
    ReleaseDetailApi,
    ReleaseSubmissionApi,
    TestCaseApi,
    ValidateReleaseApi,
)

urlpatterns = [
    path(
        "mini-program/releases/<uuid:release_id>/",
        ReleaseDetailApi.as_view(),
        name="api-mini-program-release",
    ),
    path(
        "mini-program/releases/<uuid:release_id>/prepare-demo/",
        PrepareDemoReleaseApi.as_view(),
        name="api-mini-program-prepare-demo",
    ),
    path(
        "mini-program/releases/<uuid:release_id>/artifacts/",
        ArtifactUploadApi.as_view(),
        name="api-mini-program-artifact",
    ),
    path(
        "mini-program/releases/<uuid:release_id>/checklist/<uuid:item_id>/",
        ChecklistApi.as_view(),
        name="api-mini-program-checklist",
    ),
    path(
        "mini-program/releases/<uuid:release_id>/tests/<uuid:case_id>/",
        TestCaseApi.as_view(),
        name="api-mini-program-test",
    ),
    path(
        "mini-program/releases/<uuid:release_id>/validate/",
        ValidateReleaseApi.as_view(),
        name="api-mini-program-validate",
    ),
    path(
        "mini-program/releases/<uuid:release_id>/export/",
        ExportReleaseApi.as_view(),
        name="api-mini-program-export",
    ),
    path(
        "mini-program/releases/<uuid:release_id>/submissions/",
        ReleaseSubmissionApi.as_view(),
        name="api-mini-program-submission",
    ),
]
