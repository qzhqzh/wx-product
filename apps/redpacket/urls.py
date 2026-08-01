from django.urls import path

from . import views

urlpatterns = [
    path(
        "products/red-packet-cover/",
        views.campaign_list,
        name="red-packet-list",
    ),
    path(
        "products/red-packet-cover/create/",
        views.campaign_create,
        name="red-packet-create",
    ),
    path(
        "red-packet/campaigns/<uuid:campaign_id>/",
        views.campaign_workbench,
        name="red-packet-workbench",
    ),
    path(
        "red-packet/exports/<uuid:export_id>/download/",
        views.download_export,
        name="download-red-packet-export",
    ),
]
