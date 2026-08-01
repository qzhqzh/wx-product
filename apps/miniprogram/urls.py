from django.urls import path

from . import views

urlpatterns = [
    path(
        "products/mini-program/",
        views.release_list,
        name="mini-program-list",
    ),
    path(
        "products/mini-program/create/",
        views.release_create,
        name="mini-program-create",
    ),
    path(
        "mini-program/releases/<uuid:release_id>/",
        views.release_workbench,
        name="mini-program-workbench",
    ),
    path(
        "mini-program/exports/<uuid:export_id>/download/",
        views.download_export,
        name="download-mini-program-export",
    ),
]
