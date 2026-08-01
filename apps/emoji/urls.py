from django.urls import path

from . import views

urlpatterns = [
    path("products/emoji/", views.pack_list, name="emoji-pack-list"),
    path("products/emoji/create/", views.pack_create, name="emoji-pack-create"),
    path(
        "products/emoji/prompts/",
        views.prompt_library,
        name="emoji-prompt-library",
    ),
    path(
        "products/emoji/prompts/create/",
        views.prompt_preset_create,
        name="emoji-prompt-create",
    ),
    path(
        "products/emoji/prompts/<uuid:preset_id>/update/",
        views.prompt_preset_update,
        name="emoji-prompt-update",
    ),
    path(
        "products/emoji/prompts/<uuid:preset_id>/toggle/",
        views.prompt_preset_toggle,
        name="emoji-prompt-toggle",
    ),
]
