"""
RoleBasedAccessMiddleware

Defense-in-depth backstop for the entire /admin/ namespace: even if a
future admin view is added without an @admin_required /
@permission_required decorator, this still blocks non-admins from
anything under /admin/. Per-view decorators (RAG/decorators.py) remain
the primary, fine-grained enforcement (e.g. distinguishing admin from
super_admin, or gating a specific permission); this is the coarse net
that guarantees the URL prefix itself is never exposed.
"""

from django.shortcuts import redirect, render
from django.urls import reverse

ADMIN_URL_PREFIX = "/admin/"


class RoleBasedAccessMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if request.path.startswith(ADMIN_URL_PREFIX):

            # Imported here, not at module level, so this middleware
            # (loaded before app registry setup completes) never
            # triggers an early model import.
            from .services.permission_service import is_admin

            if not request.user.is_authenticated:
                return redirect(f"{reverse('login')}?next={request.path}")

            if not is_admin(request.user):
                return render(request, "403.html", status=403)

        return self.get_response(request)


class SystemConfigSyncMiddleware:
    """
    Keeps this process's django.conf.settings in sync with the
    admin-editable SystemConfiguration row (RAG/admin/settings.html),
    on a short cache TTL - see
    RAG.services.system_config_service.apply_config_to_settings_cached()
    for why this is needed at all (separate worker processes don't
    share one process's monkey-patched settings object) and why a TTL
    check rather than a DB read on every single request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        from .services.system_config_service import apply_config_to_settings_cached

        apply_config_to_settings_cached()

        return self.get_response(request)
