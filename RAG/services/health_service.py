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


def _check_resources() -> dict:
    """
    Host CPU/memory - psutil.cpu_percent(interval=0.1) blocks for
    ~100ms (a short, deliberate sample window - psutil returns 0.0 on
    an interval-less first call, which would be a fake-looking number
    on a health page), virtual_memory() is instant. Never raises: any
    failure (psutil missing, permission error under some sandboxes)
    reports unavailable rather than taking the health endpoint down.
    """

    try:
        import psutil

        return {
            "available": True,
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_percent": psutil.virtual_memory().percent,
        }
    except Exception:
        logger.warning("Health check: CPU/memory unavailable", exc_info=True)
        return {"available": False, "cpu_percent": None, "memory_percent": None}


def _check_storage() -> dict:
    """
    Free/total disk space on the filesystem backing MEDIA_ROOT (where
    uploaded documents live) - a pure local syscall (shutil.disk_usage),
    no network, so unlike a reachability check this can't hang and needs
    no timeout. Never raises: an unreadable/missing
    path (e.g. MEDIA_ROOT not yet created) reports as unavailable
    instead of taking the health endpoint down.
    """

    try:
        usage = shutil.disk_usage(settings.MEDIA_ROOT)
        return {
            "available": True,
            "free_bytes": usage.free,
            "total_bytes": usage.total,
            "percent_free": round((usage.free / usage.total) * 100, 1) if usage.total else None,
        }
    except Exception:
        logger.warning("Health check: disk usage unavailable", exc_info=True)
        return {"available": False, "free_bytes": None, "total_bytes": None, "percent_free": None}


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
    """

    from .observability_service import get_recent_provider_status

    recent = get_recent_provider_status()
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


def _check_database() -> tuple[bool, bool, bool]:
    """
    (db_online, pgvector_enabled, embeddings_complete), all False on
    any failure. get_system_status() guards its own "SELECT 1" /
    pg_extension lookup, but its ORM count queries below that are
    not guarded - fine for settings_view (an authenticated page that
    can afford to error), not acceptable for a public health endpoint
    that has to stay up precisely when the database might not be, so
    the whole call is wrapped here instead.
    """

    try:
        system_status = get_system_status()
        return (
            system_status["db_online"],
            system_status["pgvector_enabled"],
            system_status["embeddings_complete"],
        )

    except Exception:
        logger.warning("Health check: system status unavailable", exc_info=True)
        return False, False, False


def get_health_status(live_llm_check: bool = False) -> dict:
    """
    Aggregate infra health for the /health/ endpoint (and
    manage.py check_infra), Monitoring's auto-refresh, and Monitoring's
    manual "Check Now". Never raises: each check is independent, so one
    failing component still reports the rest accurately instead of
    taking the whole endpoint down.

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

    Every *configured* LLM provider (an API key present in .env) is
    also checked - at least one of them must show a real success signal
    (ok=True, from either check) for the overall verdict, since no
    configured/working provider means the core Q&A feature can't answer
    anything regardless of how healthy the rest of the stack is. A
    provider with ok=None (no recent traffic, only possible when
    live_llm_check=False) is excluded from that requirement rather than
    counted as a failure - no data is not the same as bad data. A
    deployment with zero providers configured at all is treated the
    same as today's DB/pgvector-only check (nothing to require),
    matching "add API keys to .env" being the one manual setup step
    this app has always documented.
    """

    db_online, pgvector_enabled, embeddings_complete = _check_database()

    background_jobs = _check_background_jobs()

    llm_providers = _check_llm_providers() if live_llm_check else _recent_llm_provider_status()

    storage = _check_storage()

    resources = _check_resources()

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
        "recent_errors": _recent_errors(),
        "uptime_seconds": _uptime_seconds(),
        "live_llm_check": live_llm_check,
    }
