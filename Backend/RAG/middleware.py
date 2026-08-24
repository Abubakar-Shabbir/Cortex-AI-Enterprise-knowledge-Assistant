"""
RoleBasedAccessMiddleware

Defense-in-depth backstop for the entire /admin/ namespace: even if a
future admin view is added without an @admin_required /
@permission_required decorator, this still blocks any role holding no
admin-area permission at all from anything under /admin/. Per-view
decorators (RAG/decorators.py) remain the primary, fine-grained
enforcement (e.g. gating one specific permission); this is the coarse
net that guarantees the URL prefix itself is never exposed to a role
with zero admin-area permissions - permission-based via
has_admin_area_access (any role holding at least one of
ADMIN_AREA_PERMISSION_PREFIXES, or the Admin role), so a custom role
granted e.g. "system.view_health" passes this coarse gate and then
gets narrowed down further by the specific view's own decorator. See
RAG.services.permission_service.has_admin_area_access.
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


class RequestActivityMiddleware:
    """
    Writes one ActivityLog row per request - every page visit and
    button click that reaches Django, not just the curated set of
    business events log_activity() call sites already cover (document
    deleted, role changed, login, ...). Those specific call sites still
    win when present: activity_log_service.log_activity() flags the
    request object (_activity_logged) once it writes its own row, so
    this middleware only fills in the generic "page.<url_name>" row
    for requests nothing more specific already logged - one click,
    one row, not two.

    Placed after AuthenticationMiddleware (needs request.user) and
    wraps the full get_response() call so request.resolver_match and
    the response status code are both available by the time it logs.
    Calls log_activity(resolve_location=False) - geolocation resolution
    (RAG.services.geolocation_service) is an external HTTP call
    (ip-api.com, up to 3s on a cache miss) that this generic per-page
    row doesn't need (nothing renders city/region/country for a
    "page.*" row), so it's skipped here entirely rather than paying
    even a cache-hit lookup on every single request; the curated
    call sites (login, document delete, role change, ...) still
    resolve it by default, since Profile's login history genuinely
    displays it. The DB write itself still happens unconditionally -
    see the module docstring on ActivityLog for the retention/volume
    tradeoff this implies.
    """

    EXCLUDED_PATH_PREFIXES = ("/static/", "/media/", "/health/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        response = self.get_response(request)

        if request.path.startswith(self.EXCLUDED_PATH_PREFIXES):
            return response

        if request.method in ("OPTIONS", "HEAD"):
            return response

        if getattr(request, "_activity_logged", False):
            return response

        # Imported here, not at module level, for the same reason
        # RoleBasedAccessMiddleware imports permission_service inline -
        # this middleware loads before the app registry is ready.
        from .services.activity_log_service import log_activity

        url_name = request.resolver_match.url_name if request.resolver_match else None
        action = f"page.{url_name}" if url_name else "page.unmatched"

        actor = request.user if getattr(request, "user", None) and request.user.is_authenticated else None
        actor_label = actor.username if actor else "anonymous"

        log_activity(
            actor=actor,
            action=action[:50],
            description=f"{actor_label} {request.method} {request.path} → {response.status_code}"[:255],
            request=request,
            resolve_location=False,
        )

        return response


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

        # Best place to kick off the reranker's one-time model load in
        # the background (see reranker_service.ensure_warm_started) -
        # same "runs on every request, cheap after the first" shape
        # this middleware already has for settings sync, and - unlike
        # AppConfig.ready() - never fires for a bare `manage.py`
        # command that isn't actually serving requests.
        from .services.reranker_service import ensure_warm_started as ensure_reranker_warm_started

        ensure_reranker_warm_started()

        # Same warm-up shape for the core embedding model
        # (embedding_service.py) - unlike the reranker this isn't
        # behind a feature flag, since every upload/query needs it,
        # but it's still loaded lazily rather than at import time (see
        # embedding_service._get_model's docstring), so this is what
        # actually loads it in the common case: on this process's
        # first request (almost always Railway's own deploy health
        # check) rather than blocking the process from binding to
        # $PORT at all.
        from .services.embedding_service import ensure_warm_started as ensure_embedding_warm_started

        ensure_embedding_warm_started()

        return self.get_response(request)
