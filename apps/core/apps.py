from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "流水线底座"

    def ready(self):
        from .media_hardening import install_media_hardening

        install_media_hardening()

        from . import signals  # noqa: F401
        from .task_hardening import install_task_hardening

        install_task_hardening()
