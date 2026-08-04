"""
Health checks (Sprint 10).

Backs the public /health/ endpoint (RAG.views.health_check) used by
Docker/orchestrator liveness and readiness probes. Reuses
stats_service.get_system_status() for the DB/pgvector checks it
already performs rather than duplicating that SELECT 1 / pg_extension
lookup, and adds the one infra check Sprint 10 introduces: Redis
(the same instance backs both the Celery broker and, when
USE_REDIS_CACHE is on, Django's cache - see settings.REDIS_URL).
"""

import logging

from django.conf import settings

from .stats_service import get_system_status

logger = logging.getLogger(__name__)


def _check_redis() -> bool:
    """
    True if Redis at settings.REDIS_URL answers a PING within a short
    timeout. Never raises or hangs the health endpoint: connection
    errors and timeouts are caught and logged, not propagated.
    """

    try:
        import redis

        client = redis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1,
            socket_timeout=1,
        )

        return bool(client.ping())

    except Exception:
        logger.warning("Health check: Redis unreachable", exc_info=True)
        return False


def _check_celery_workers() -> int:
    """
    Number of Celery workers that responded to a broker PING within a
    short timeout, or 0 if none did / the broker is unreachable. Only
    called when settings.ENABLE_ASYNC_PROCESSING is on (see
    get_health_status()) - skipped otherwise so the common default-off
    case never pays for a broker round trip on the health-check path.
    """

    try:
        from myproject.celery import app as celery_app

        replies = celery_app.control.inspect(timeout=1.0).ping() or {}

        return len(replies)

    except Exception:
        logger.warning("Health check: Celery broker unreachable", exc_info=True)
        return 0


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


def get_health_status() -> dict:
    """
    Aggregate infra health for the /health/ endpoint. Never raises:
    each check is independent, so one failing component still reports
    the rest accurately instead of taking the whole endpoint down.

    Redis is only load-bearing to the overall "ok"/"degraded" verdict
    when a feature that actually depends on it is enabled
    (settings.USE_REDIS_CACHE or settings.ENABLE_ASYNC_PROCESSING) -
    an unreachable Redis shouldn't fail the health check on a
    deployment that never turned either on.
    """

    db_online, pgvector_enabled, embeddings_complete = _check_database()

    redis_reachable = _check_redis()

    celery_workers = _check_celery_workers() if settings.ENABLE_ASYNC_PROCESSING else None

    checks = {
        "database": db_online,
        "pgvector": pgvector_enabled,
        "redis": redis_reachable,
    }

    healthy = checks["database"] and checks["pgvector"]

    if settings.USE_REDIS_CACHE or settings.ENABLE_ASYNC_PROCESSING:
        healthy = healthy and redis_reachable

    if settings.ENABLE_ASYNC_PROCESSING:
        healthy = healthy and bool(celery_workers)

    return {
        "status": "ok" if healthy else "degraded",
        "checks": checks,
        "celery_workers": celery_workers,
        "embeddings_complete": embeddings_complete,
    }
