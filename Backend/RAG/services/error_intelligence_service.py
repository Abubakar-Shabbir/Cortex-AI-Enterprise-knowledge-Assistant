"""
Error Intelligence

Automatic, app-wide error capture and grouping - the "reuse the logging
system instead of re-instrumenting the app" design: ErrorCaptureHandler
is a standard logging.Handler wired into settings.LOGGING (see that
file's LOGGING dict), so every logger.warning()/error()/exception() call
already scattered across ~25 files (auth, RBAC, documents, retrieval
stages, background jobs, LLM providers, unhandled exceptions) starts
flowing into RAG.models.ErrorGroup automatically, with zero changes to
any individual call site - the same "wrap once, capture everywhere"
approach RAG.services.perf.timed_stage() already uses for stage timing.

This module owns two things:
- redact_secrets(): the one place secret-scrubbing happens before
  anything is ever persisted.
- ErrorCaptureHandler: the logging.Handler itself, plus the read-side
  query helpers the System Logs page (RAG.views.admin_system_logs_view)
  uses for its Error Groups tab.
"""

import hashlib
import logging
import re

logger_self_name = __name__  # never log through this module's own logger from inside emit() - see its docstring for why.

_SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(r"AIza[A-Za-z0-9_-]{20,}"),  # Google API key shape (Gemini)
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{16,}", re.IGNORECASE),
    re.compile(r"\b(api[_-]?key|password|passwd|secret|token)\b\s*[=:]\s*['\"]?[^\s'\"]{6,}", re.IGNORECASE),
]

_REDACTED = "[REDACTED]"


def _configured_secret_values():
    """The actual current secret values this deployment holds - defense in depth beyond the regex patterns above, in case one leaks into a message verbatim without matching any recognizable shape (e.g. a DB password with no special pattern)."""

    from django.conf import settings

    values = [
        getattr(settings, "GEMINI_API_KEY", ""),
        getattr(settings, "OPENROUTER_API_KEY", ""),
        getattr(settings, "GROQ_API_KEY", ""),
        getattr(settings, "SECRET_KEY", ""),
        settings.DATABASES.get("default", {}).get("PASSWORD", ""),
    ]

    # Skip empty/trivially short values - redacting "" or a 2-char
    # placeholder would corrupt unrelated text via accidental substring
    # matches.
    return [v for v in values if v and len(v) >= 6]


def redact_secrets(text: str) -> str:
    """Never log API keys, passwords, tokens, or secrets - called on every message before it's persisted to ErrorGroup. Safe to call on already-clean text (a no-op if nothing matches)."""

    if not text:
        return text

    redacted = text

    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)

    for value in _configured_secret_values():
        redacted = redacted.replace(value, _REDACTED)

    return redacted


class ErrorCaptureHandler(logging.Handler):
    """
    Standard logging.Handler - wired into settings.LOGGING alongside
    (not replacing) the existing "console" handler. Upserts one
    ErrorGroup row per distinct (logger, level, error shape), never
    raises (a logging handler that crashes must never break the app
    it's logging), and degrades to a silent no-op before the DB is
    ready (management commands run before migrations, etc.) the same
    way RAG.services.system_config_service.apply_config_to_settings()
    already does for the same reason.

    Deliberately does not log anything from inside emit() itself - a
    handler that logs its own failures risks a recursive logging loop
    the moment its own log call also fails.
    """

    def emit(self, record):

        try:
            self._emit(record)
        except Exception:
            pass

    def _emit(self, record):

        from django.db import models as django_models
        from django.utils import timezone

        from ..models import ErrorGroup
        from .trace import get_trace_id

        error_type = ""
        if record.exc_info and record.exc_info[0] is not None:
            error_type = record.exc_info[0].__name__

        message = redact_secrets(record.getMessage())[:2000]

        fingerprint_source = f"{record.name}:{record.levelname}:{error_type or message[:200]}"
        fingerprint = hashlib.sha256(fingerprint_source.encode()).hexdigest()

        trace_id = get_trace_id()
        now = timezone.now()
        occurrence = {"trace_id": trace_id, "timestamp": now.isoformat()} if trace_id else None

        group, created = ErrorGroup.objects.get_or_create(
            fingerprint=fingerprint,
            defaults={
                "logger_name": record.name,
                "level": record.levelname,
                "error_type": error_type,
                "message": message,
                "occurrence_count": 1,
                "last_seen": now,
                "recent_occurrences": [occurrence] if occurrence else [],
            },
        )

        if created:
            return

        recent = list(group.recent_occurrences or [])
        if occurrence:
            recent.append(occurrence)
            recent = recent[-20:]

        ErrorGroup.objects.filter(pk=group.pk).update(
            occurrence_count=django_models.F("occurrence_count") + 1,
            last_seen=now,
            recent_occurrences=recent,
        )


# ============================================================
# Read side - Logs page / System Health integration
# ============================================================

def list_error_groups(filters: dict = None, page_size: int = 25, page: int = 1):
    """Filtered/paginated ErrorGroup queryset for the Logs page's Error Groups tab. `filters`: logger_name (icontains), level, q (message icontains), date_from, date_to."""

    from ..models import ErrorGroup

    filters = filters or {}
    qs = ErrorGroup.objects.all()

    if filters.get("logger_name"):
        qs = qs.filter(logger_name__icontains=filters["logger_name"])
    if filters.get("level"):
        qs = qs.filter(level=filters["level"])
    if filters.get("q"):
        qs = qs.filter(message__icontains=filters["q"])
    if filters.get("date_from"):
        qs = qs.filter(last_seen__date__gte=filters["date_from"])
    if filters.get("date_to"):
        qs = qs.filter(last_seen__date__lte=filters["date_to"])

    total = qs.count()
    start = (page - 1) * page_size

    return {
        "results": list(qs[start:start + page_size]),
        "total": total,
        "page": page,
        "page_size": page_size,
        "num_pages": max(1, -(-total // page_size)),
    }


def recent_errors_for_module(module_prefix: str, minutes: int = 60, limit: int = 5):
    """
    ErrorGroups whose logger_name starts with `module_prefix` and were
    last seen within the last `minutes` - System Health's per-service
    "recent errors" panel (health_service._recent_errors()) uses this
    to show background-job/DB failures that already flow into
    ErrorGroup via their own existing logger.exception() calls, no new
    instrumentation needed.
    """

    from datetime import timedelta

    from django.utils import timezone

    from ..models import ErrorGroup

    cutoff = timezone.now() - timedelta(minutes=minutes)

    return list(
        ErrorGroup.objects.filter(logger_name__startswith=module_prefix, last_seen__gte=cutoff).order_by("-last_seen")[:limit]
    )
