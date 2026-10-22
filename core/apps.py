from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = "core"
    verbose_name = "Pondo core"

    def ready(self):
        from . import login_log  # noqa: F401 – writes the login register
