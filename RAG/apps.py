from django.apps import AppConfig


class RagConfig(AppConfig):
    name = 'RAG'

    def ready(self):
        """
        Apply any admin-saved SystemConfiguration on top of settings.py
        as soon as this process starts - covers processes that never
        go through RAG.middleware.SystemConfigSyncMiddleware (Celery
        workers, management commands). Never raises: on a management
        command that runs before migrations exist yet (e.g. the very
        first `makemigrations`), this degrades to settings.py's own
        defaults rather than failing the command - see
        system_config_service.apply_config_to_settings()'s own
        try/except.
        """

        from .services.system_config_service import apply_config_to_settings

        apply_config_to_settings()
