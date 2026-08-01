from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path(
        "login/",
        auth_views.LoginView.as_view(template_name="registration/login.html"),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("", include("apps.emoji.urls")),
    path("", include("apps.redpacket.urls")),
    path("", include("apps.miniprogram.urls")),
    path("", include("apps.core.urls")),
    path("api/v1/", include("apps.emoji.api_urls")),
    path("api/v1/", include("apps.redpacket.api_urls")),
    path("api/v1/", include("apps.miniprogram.api_urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
