from django.urls import path

from . import views

urlpatterns = [
    path("health/", views.health, name="health"),
    path("", views.dashboard, name="dashboard"),
    path("projects/", views.project_list, name="project-list"),
    path("projects/create/", views.project_create, name="project-create"),
    path("projects/<uuid:project_id>/", views.project_detail, name="project-detail"),
    path("projects/<uuid:project_id>/packs/create/", views.pack_create, name="pack-create"),
    path("packs/<uuid:pack_id>/", views.pack_workbench, name="pack-workbench"),
    path("products/<slug:code>/", views.product_placeholder, name="product-placeholder"),
    path("exports/<uuid:export_id>/download/", views.download_export, name="download-export"),
    path("assets/<uuid:asset_id>/view/", views.view_asset, name="view-asset"),
]
