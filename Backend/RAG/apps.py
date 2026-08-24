from django.apps import AppConfig
from django.db.models.signals import post_save


class RagConfig(AppConfig):
    name = 'RAG'

    def ready(self):
        """
        Deliberately does NOT query the database (e.g. no
        SystemConfiguration read) - Django's own guidance is that
        AppConfig.ready() runs during app initialization, before it's
        safe to assume a DB connection is even available (a management
        command run before the first migration, a process still coming
        up), and doing so here reliably produced Django's own
        "Accessing the database during app initialization is
        discouraged" RuntimeWarning on every process start.

        The one thing that used to live here - applying an admin-saved
        SystemConfiguration on top of settings.py - is instead covered
        per-consumer: RAG.middleware.SystemConfigSyncMiddleware already
        does it on every web request (before this process's very first
        view runs), and RAG.tasks.process_document_task/run_ai_task
        each call apply_config_to_settings_cached() at the top of the
        task body for the background thread pool case, which never goes
        through that middleware. Both reuse the same 15s cache TTL, so
        neither pays a DB round trip on every call.
        """

        post_save.connect(_attach_new_permission_to_admin_role, sender="RAG.Permission")
        post_save.connect(_create_profile_for_new_user, sender="auth.User")


def _create_profile_for_new_user(sender, instance, created, **kwargs):
    """
    Guarantees every new account gets a UserProfile row immediately, so
    request.user.profile never raises RelatedObjectDoesNotExist. Accounts
    that existed before UserProfile did are backfilled lazily instead -
    every view that touches a profile calls get_or_create() defensively,
    the same "idempotent, safe to backfill lazily" approach seed_rbac.py
    already uses for role assignment.
    """

    if not created:
        return

    from .models import UserProfile

    UserProfile.objects.get_or_create(user=instance)


def _attach_new_permission_to_admin_role(sender, instance, created, **kwargs):
    """
    Keeps the Admin role's Role.permissions M2M table honest as new
    Permission rows appear (via seed_rbac or the Django Admin) -
    Role.has_permission() already grants Admin every permission in
    code regardless of this table, so this is purely so the Role
    Management UI's checkboxes for Admin always show fully checked
    instead of looking out of date.
    """

    if not created:
        return

    from .models import ADMIN_ROLE_SLUG, Role

    admin_role = Role.objects.filter(slug=ADMIN_ROLE_SLUG).first()

    if admin_role:
        admin_role.permissions.add(instance)
