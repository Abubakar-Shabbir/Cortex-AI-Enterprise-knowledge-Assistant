"""
RoleBasedAccessMiddleware

Defense-in-depth backstop for the entire /admin/ namespace: even if a
future admin view is added without an @admin_required /
@permission_required decorator, this still blocks any role holding
none of the admin-area permissions from anything under /admin/.
Per-view decorators (RAG/decorators.py) remain the primary,
fine-grained enforcement (e.g. gating one specific permission); this is
the coarse net that guarantees the URL prefix itself is never exposed
to a role with zero admin-area access - see
RAG.services.permission_service.has_admin_area_access /
ADMIN_AREA_PERMISSIONS for what counts.
"""

from django.shortcuts import redirect, render
from django.urls import reverse

from .services.trace import bind_trace_id

ADMIN_URL_PREFIX = "/admin/"


class RequestTraceMiddleware:
    """
    Binds one trace ID for the whole request/response cycle
    (RAG.services.trace.bind_trace_id()), so log correlation
    (TraceIdLogFilter, settings.LOGGING) and automatic error capture
    (RAG.services.error_intelligence_service.ErrorCaptureHandler) work
    for EVERY view - login, document upload, RBAC checks, AI Task
    creation - not just Ask AI. Placed early in MIDDLEWARE (right after
    SecurityMiddleware) so as much of the request as possible - and
    every logger call any later middleware/view makes - falls inside
    the bound scope.

    ask_ai/ask_ai_stream (RAG/views.py) already bind their own trace_id
    and are deliberately left untouched: ask_ai_stream in particular
    has to bind *inside* its own generator function, since a streaming
    response's body is only actually iterated by Django after this
    middleware has already returned - a middleware-level bind alone can
    never cover it (see that view's own comment). Ask AI ends up with
    two nested trace IDs as a result (this middleware's, then its own,
    more specific one) - harmless; contextvars nesting restores the
    outer value correctly once the inner one exits.

    Sets X-Request-ID on the response so a user (or support) can hand
    back the exact ID a request logged/failed under.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        with bind_trace_id() as trace_id:
            request.trace_id = trace_id
            response = self.get_response(request)
            response["X-Request-ID"] = trace_id

        return response


class RoleBasedAccessMiddleware:

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        if request.path.startswith(ADMIN_URL_PREFIX):

            # Imported here, not at module level, so this middleware
            # (loaded before app registry setup completes) never
            # triggers an early model import.
            from .services.permission_service import has_admin_area_access

            if not request.user.is_authenticated:
                return redirect(f"{reverse('login')}?next={request.path}")

            if not has_admin_area_access(request.user):
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
