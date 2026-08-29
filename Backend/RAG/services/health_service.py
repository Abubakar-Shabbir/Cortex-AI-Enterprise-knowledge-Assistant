"""
Health checks (Sprint 10, background-pool check replaced Redis/Celery in
the free-tier refactor).

Backs the public /health/ endpoint (RAG.views.health_check) used by
Docker/orchestrator liveness and readiness probes. Reuses
stats_service.get_system_status() for the DB/pgvector checks it
already performs rather than duplicating that SELECT 1 / pg_extension
lookup, and adds a check against the in-process background thread pool
(RAG.services.task_runner) that now runs document processing and AI
Tasks instead of a separate Celery worker.
"""

import logging
import shutil
import time

from django.conf import settings

from .llm_client import PROVIDER_REGISTRY, _is_configured, get_llm
from .stats_service import get_system_status

logger = logging.getLogger(__name__)

# Captured once at import time (process start), not per-call - this is
# what "process uptime" means below. Never raises: unlike the network
# checks in this module, module import failing would take the whole
# app down anyway, so no try/except is needed here.
_PROCESS_STARTED_AT = time.time()

# Module-name prefixes (as they appear in logger_name, i.e.
# logging.getLogger(__name__) inside each of these files) each health
# card's "recent errors" panel should pull from - maps a card to the
# ErrorGroup rows that already flow in from that code's existing
# logger.exception()/warning() calls, no new instrumentation needed.
_SERVICE_MODULE_PREFIXES = {
    "database": ("RAG.services.stats_service", "django.db"),
    "background_jobs": ("RAG.tasks", "RAG.services.task_runner"),
    "llm_providers": ("RAG.services.llm_client", "RAG.services.llm_service"),
}


def _check_resources(blocking: bool = True) -> dict:
    """
    Host CPU/memory - virtual_memory() is instant; cpu_percent()'s cost
    depends on `blocking`.

    `blocking=True` (Monitoring's own dashboard render, called rarely
    by a human) samples over interval=0.1 - a deliberate ~100ms wait so
    the number reflects real recent usage instead of psutil's "0.0 on
    an interval-less first call" default.

    `blocking=False` (the public /health/ endpoint - see
    get_health_status()'s `light` param) uses interval=None instead:
    non-blocking, comparing against psutil's own internal last-call
    timestamp. An orchestrator like Railway can poll /health/ many
    times a second during a deploy; paying a guaranteed 100ms sleep on
    every single poll is exactly the kind of avoidable latency that
    turns into a health-check/upstream timeout, for a number this
    endpoint doesn't even gate its `healthy` verdict on (see below).

    Never raises: any failure (psutil missing, permission error under
    some sandboxes) reports unavailable rather than taking the health
    endpoint down.
    """

    try:
        import psutil

        return {
            "available": True,
            "cpu_percent": psutil.cpu_percent(interval=0.1 if blocking else None),
            "memory_percent": psutil.virtual_memory().percent,
        }
    except Exception:
        logger.warning("Health check: CPU/memory unavailable", exc_info=True)
        return {"available": False, "cpu_percent": None, "memory_percent": None}


def _check_storage() -> dict:
    """
    settings.USE_S3_STORAGE (media uploads on S3-compatible object
    storage - see settings.py's own comment) reports "available" without
    a disk-usage figure: MEDIA_ROOT/shutil.disk_usage would be reading
    the free-tier host's local ephemeral disk, which no longer has
    anything to do with where documents actually live, and a live
    network probe of the bucket isn't worth adding to a public,
    frequently-polled endpoint (this app has no cheap "free space
    remaining" API call for S3-compatible storage anyway) - a genuine
    outage there still surfaces through upload/download failures
    themselves (RAG.services.upload_service, ErrorGroup).
    Otherwise (FileSystemStorage, the local-dev/persistent-disk default)
    unchanged from before: free/total disk space on the filesystem
    backing MEDIA_ROOT - a pure local syscall (shutil.disk_usage), no
    network, so unlike a reachability check this can't hang and needs no
    timeout. Never raises: an unreadable/missing path (e.g. MEDIA_ROOT
    not yet created) reports as unavailable instead of taking the health
    endpoint down.
    """

    if settings.USE_S3_STORAGE:
        return {"available": True, "backend": "s3", "free_bytes": None, "total_bytes": None, "percent_free": None}

    try:
        usage = shutil.disk_usage(settings.MEDIA_ROOT)
        return {
            "available": True,
            "backend": "local",
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            "percent_free": round((usage.free / usage.total) * 100, 1) if usage.total else None,
        }
    except Exception:
        logger.warning("Health check: disk usage unavailable", exc_info=True)
        return {"available": False, "backend": "local", "free_bytes": None, "total_bytes": None, "percent_free": None}


def _uptime_seconds() -> int:
    return round(time.time() - _PROCESS_STARTED_AT)


def _check_background_jobs() -> dict:
    """
    Status of the in-process background thread pool
    (RAG.services.task_runner) that runs document processing (when
    settings.ENABLE_ASYNC_PROCESSING is on) and AI Task execution
    (always). Unlike the old Celery-worker check this replaced, there's
    no "is it reachable" question - the pool lives in this same
    process, so it's available whenever this process is up. Never
    raises: any failure reports unavailable rather than taking the
    health endpoint down.
    """

    try:
        from .task_runner import get_status

        return get_status()

    except Exception:
        logger.warning("Health check: background task pool status unavailable", exc_info=True)
        return {"available": False, "max_workers": None, "active": None, "pending": None}


def _check_llm_providers() -> dict:
    """
    {provider_name: {"ok": bool, "latency_ms": int|None, "message": str}}
    for every provider that has an API key configured (PROVIDER_REGISTRY,
    llm_client.py) - each checked via the same LLMClient.health_check()
    the Settings page's "Test Connection" button already uses, so this
    is a real minimal generate() call per provider, not just a
    key-presence check. Never raises: a provider erroring out just
    reports ok=False for that provider, same never-fail-the-whole-check
    contract as _check_background_jobs() above. An
    unconfigured provider (no key) is omitted entirely rather than
    reported False - "not set up" and "set up but broken" are different
    situations, and only the latter should look like a problem here.

    Kept as the *manual* check (RAG.views.monitoring_check_now) - see
    get_health_status()'s own docstring for why the auto-refresh path
    no longer calls this on every poll.
    """

    llm = get_llm()
    results = {}

    for provider in PROVIDER_REGISTRY:
        if not _is_configured(provider):
            continue

        try:
            results[provider] = llm.health_check(provider)
        except Exception:
            logger.warning("Health check: LLM provider '%s' check failed", provider, exc_info=True)
            results[provider] = {"ok": False, "latency_ms": None, "message": "Health check failed unexpectedly."}

    return results


def _recent_llm_provider_status() -> dict:
    """
    Same {provider: {"ok", "latency_ms", "message"}} shape as
    _check_llm_providers() above, but derived from real recent Ask AI/
    AI Task traffic (observability_service.get_recent_provider_status())
    instead of a live API call - this is what the auto-refresh path
    uses. Every *configured* provider still gets an entry even with zero
    recent traffic ("No recent data"), so the UI never silently drops a
    provider the live check would have shown.

    Never raises, unlike a previous version of this function - every
    other check in this module already followed that contract
    (_check_database, _check_background_jobs, _check_storage,
    _check_resources), but this one called
    observability_service.get_recent_provider_status() (a real DB
    query, AIRequestTrace) unguarded. A DB outage - the exact condition
    /health/ exists to report - used to turn into an unhandled 500 from
    this function instead of a clean "degraded" JSON response, which is
    worse for a platform healthcheck than a slow response: Railway
    (or any orchestrator) sees an unexpected error rather than a
    legible signal. An empty dict here is inert - get_health_status()
    already treats "no LLM data" as "nothing to require", not a
    failure, the same way it treats a provider with ok=None.
    """

    from .observability_service import get_recent_provider_status

    try:
        recent = get_recent_provider_status()
    except Exception:
        logger.warning("Health check: recent LLM provider status unavailable", exc_info=True)
        return {}

    results = {}

    for provider in PROVIDER_REGISTRY:
        if not _is_configured(provider):
            continue
        results[provider] = recent.get(provider) or {
            "ok": None, "latency_ms": None, "message": "No requests in the last 15 minutes - use Check Now for a live check.",
        }

    return results


def _recent_errors(minutes: int = 60) -> dict:
    """
    {service_key: [ErrorGroup, ...]} for each entry in
    _SERVICE_MODULE_PREFIXES - background-job/DB/LLM-provider failures
    that already flow into ErrorGroup via their own existing
    logger.exception()/warning() calls (this module's own
    _check_background_jobs(), llm_client.py's provider clients, etc.) -
    no new instrumentation needed. Never raises: a lookup failure for
    one service reports an empty list for that card rather than
    breaking the whole health page.
    """

    from .error_intelligence_service import recent_errors_for_module

    results = {}

    for service, prefixes in _SERVICE_MODULE_PREFIXES.items():
        groups = []
        try:
            for prefix in prefixes:
                groups.extend(recent_errors_for_module(prefix, minutes=minutes, limit=5))
        except Exception:
            logger.warning("Health check: recent-errors lookup failed for '%s'", service, exc_info=True)
        groups.sort(key=lambda g: g.last_seen, reverse=True)
        results[service] = groups[:5]

    return results


def _check_database(minimal: bool = False) -> tuple[bool, bool, bool]:
    """
    (db_online, pgvector_enabled, embeddings_complete), all False on
    any failure. get_system_status() guards its own "SELECT 1" /
    pg_extension lookup, but its ORM count queries below that are
    not guarded - fine for settings_view (an authenticated page that
    can afford to error), not acceptable for a public health endpoint
    that has to stay up precisely when the database might not be, so
    the whole call is wrapped here instead.

    `minimal=True` forwards to get_system_status(minimal=True), which
    skips the total_documents/total_storage/LLM-provider-config queries
    this function never reads anyway - see that function's docstring.
    """

    try:
        system_status = get_system_status(minimal=minimal)
        return (
            system_status["db_online"],
            system_status["pgvector_enabled"],
            system_status["embeddings_complete"],
        )

    except Exception:
        logger.warning("Health check: system status unavailable", exc_info=True)
        return False, False, False


def get_health_status(live_llm_check: bool = False, light: bool = False) -> dict:
    """
    Aggregate infra health for the /health/ endpoint (and
    manage.py check_infra), Monitoring's auto-refresh, and Monitoring's
    manual "Check Now". Never raises: each check is independent, so one
    failing component still reports the rest accurately instead of
    taking the whole endpoint down.

    `light=True` (RAG.views.health_check only - a public endpoint an
    orchestrator like Railway polls repeatedly during every deploy)
    drops every check that costs real time but whose result the caller
    doesn't use: `_recent_errors()` is skipped outright (health_check's
    own JSON payload already excludes it), `_check_resources()` samples
    CPU non-blocking instead of sleeping ~100ms, and `_check_database()`
    skips the count/aggregate queries only the full settings_view/
    monitoring.html dashboard reads. None of this changes `status` -
    the same database/pgvector/background_jobs/llm_providers signals
    still gate it - it just removes work whose output was being
    computed and thrown away on every single poll.

    `live_llm_check` picks which of two provider-status sources is used
    - both return the identical {provider: {ok, latency_ms, message}}
    shape, so nothing downstream (this function's own status logic,
    monitoring.html) needs to know which one ran:
    - False (default - /health/, auto-refresh, check_infra): derives
      status from real recent Ask AI/AI Task traffic
      (_recent_llm_provider_status(), zero API cost) - safe to poll
      every 15 seconds or from an orchestrator's liveness probe without
      burning provider quota just from the check itself.
    - True (Monitoring's manual "Check Now" button only): the original
      live synchronous generate() call per provider
      (_check_llm_providers()) - a real-time answer, on demand.

    Every *configured* LLM provider (an API key present in .eee) is
    also checked - at least one of them must show a real success signal
    (ok=True, from either check) for the overall verdict, since no
    configured/working provider means the core Q&A feature can't answer
    anything regardless of how healthy the rest of the stack is. A
    provider with ok=None (no recent traffic, only possible when
    live_llm_check=False) is excluded from that requirement rather than
    counted as a failure - no data is not the same as bad data. A
    deployment with zero providers configured at all is treated the
    same as today's DB/pgvector-only check (nothing to require),
    matching "add API keys to .eee" being the one manual setup step
    this app has always documented.
    """

    db_online, pgvector_enabled, embeddings_complete = _check_database(minimal=light)

    background_jobs = _check_background_jobs()

    llm_providers = _check_llm_providers() if live_llm_check else _recent_llm_provider_status()

    storage = _check_storage()

    resources = _check_resources(blocking=not light)

    checks = {
        "database": db_online,
        "pgvector": pgvector_enabled,
        "background_jobs": background_jobs["available"],
        "llm_providers": llm_providers,
        "storage": storage["available"],
    }

    healthy = checks["database"] and checks["pgvector"] and checks["background_jobs"]

    llm_ok_signals = [result["ok"] for result in llm_providers.values() if result["ok"] is not None]
    if llm_ok_signals:
        healthy = healthy and any(llm_ok_signals)

    # A near-full disk isn't a hard "degraded" the way an unreachable DB
    # is (the app still answers questions fine), but it's worth a
    # distinct status tier so Monitoring can flag it before it becomes
    # an upload-time failure.
    if storage["percent_free"] is not None and storage["percent_free"] < 5:
        status = "critical"
    else:
        status = "ok" if healthy else "degraded"

    return {
        "status": status,
        "checks": checks,
        "background_jobs": background_jobs,
        "embeddings_complete": embeddings_complete,
        "storage": storage,
        "resources": resources,
        "recent_errors": {} if light else _recent_errors(),
        "uptime_seconds": _uptime_seconds(),
        "live_llm_check": live_llm_check,
    }
