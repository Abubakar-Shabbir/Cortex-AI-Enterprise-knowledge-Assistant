"""
Shared AI observability - the one place that turns per-request stage
timing (RAG.services.trace.get_stages()) and LLM call metadata
(RAG.services.llm_client.get_last_llm_meta()) into a persisted,
queryable AIRequestTrace row, and the one place that reads them back
for the AI Logs page / Analytics' Performance section.

save_trace() is called from both RAG.services.query_service.py (Ask AI)
and RAG.tasks.run_ai_task (AI Tasks) - this is deliberately the single
integration point both features share, rather than each feature having
its own trace-persistence logic.
"""

import logging

from django.db.models import Aggregate, Avg, Count, FloatField, Q

from ..models import AIRequestTrace
from .llm_client import get_last_llm_meta
from .trace import get_stages

logger = logging.getLogger(__name__)


class PercentileCont(Aggregate):
    """PostgreSQL PERCENTILE_CONT(p) WITHIN GROUP (ORDER BY expr) - this app is Postgres-only (see myproject/settings.py's DATABASES), so this is safe to rely on directly rather than approximating percentiles in Python."""

    function = "PERCENTILE_CONT"
    name = "percentile_cont"
    output_field = FloatField()
    template = "%(function)s(%(percentile)s) WITHIN GROUP (ORDER BY %(expressions)s)"

    def __init__(self, expression, percentile, **extra):
        super().__init__(expression, percentile=percentile, **extra)


# Groups multiple raw timed_stage() labels (some of which are
# concurrent siblings - e.g. vector/BM25/graph search all run in
# parallel via ThreadPoolExecutor) into the coarse pipeline phases a
# human wants a bottleneck answer in terms of. Retrieval takes the MAX
# of its members (parallel wall time is bounded by the slowest branch,
# not their sum) - every other group currently has one member, but is
# still expressed as a group for the same max-based logic and so a
# finer future breakdown (e.g. splitting "LLM request TOTAL" into
# prompt-build/network/parse) drops in with no format change.
#
# Umbrella stages that wrap other recorded stages rather than
# representing real work of their own ("request processing (ask_ai)
# TOTAL", "AI Task run TOTAL") are deliberately absent from every group
# below - including them would trivially "win" bottleneck detection
# every time, since they're the largest by construction.
STAGE_GROUPS = {
    "Retrieval": {
        "vector search", "hybrid search (BM25)", "knowledge graph retrieval",
        "HyDE retrieval", "multi-query retrieval", "query expansion", "reranking",
        "BM25 index build (cache miss)", "BM25 scoring",
        "graph entity scope build (cache miss)",
    },
    "Embedding": {"embedding generation"},
    "Context Assembly": {"context assembly", "AI Task context extraction"},
    "LLM Generation": {"LLM request TOTAL", "LLM request TOTAL (streamed)", "AI Task LLM call"},
    "Citation Validation": {"citation validation"},
}


def compute_bottleneck(stages: list, total_duration_ms: int = 0) -> tuple:
    """
    (group_key, human_label, duration_ms, percent_of_total) for
    whichever STAGE_GROUPS bucket accounts for the most time. Durations
    are first summed per stage NAME - AI Tasks calls "AI Task LLM call"
    once per document, sequentially, so those must add up rather than
    only reporting the single slowest document - then the max is taken
    ACROSS distinct names within a group, since those represent
    concurrent alternatives (e.g. Ask AI's "vector search" vs "hybrid
    search (BM25)" vs "knowledge graph retrieval" all run in parallel
    via ThreadPoolExecutor - the slowest one bounds the group's wall
    time, they don't add up). Returns ("", "", 0, 0.0) when there's
    nothing to compare (e.g. every stage failed before any
    timed_stage() ran).
    """

    per_name_total = {}
    for stage in stages:
        per_name_total[stage["name"]] = per_name_total.get(stage["name"], 0.0) + stage["duration_ms"]

    best_group, best_ms = "", 0.0

    for group, member_names in STAGE_GROUPS.items():
        group_max = max(
            (per_name_total[name] for name in member_names if name in per_name_total),
            default=0.0,
        )
        if group_max > best_ms:
            best_group, best_ms = group, group_max

    if not best_group:
        return "", "", 0, 0.0

    percent = round((best_ms / total_duration_ms) * 100, 1) if total_duration_ms else 0.0

    return best_group, best_group, round(best_ms), percent


def save_trace(
    trace_id: str,
    source: str,
    user=None,
    *,
    query_log=None,
    ai_task_run=None,
    status: str,
    total_duration_ms: int = None,
    retrieved_chunks: int = 0,
    citation_count: int = 0,
    error: Exception = None,
) -> AIRequestTrace:
    """
    Assembles and persists one AIRequestTrace row from whatever's
    currently recorded in this context (get_stages()) plus the most
    recent LLM call's metadata (get_last_llm_meta()) - never raises
    (a tracing failure must never break the real Ask AI answer / AI
    Task run it's describing), logs and returns None on any error.

    `error`, if given, takes priority for error_type/error_message over
    whatever get_last_llm_meta() reported (a non-LLM failure - e.g. a
    retrieval/DB exception - is more specific than a stale LLM-layer
    error from an earlier successful call in the same context).
    """

    try:
        stages = get_stages()
        llm_meta = get_last_llm_meta() or {}

        duration = total_duration_ms if total_duration_ms is not None else round(
            sum(s["duration_ms"] for s in stages)
        )

        bottleneck_stage, bottleneck_label, _, _ = compute_bottleneck(stages, duration)

        # Cache-hit is only a meaningful concept for Ask AI's retrieval
        # cache (retrieve_chunks()) - inferred rather than passed in,
        # since a cache hit skips the whole ThreadPoolExecutor fan-out
        # and so none of its member stages ever get recorded at all.
        cache_hit = None
        if source == AIRequestTrace.Source.ASK_AI:
            cache_hit = retrieved_chunks > 0 and not any(
                s["name"] in STAGE_GROUPS["Retrieval"] for s in stages
            )

        error_type = llm_meta.get("error_type", "")
        error_message = llm_meta.get("error_message", "")

        if error is not None:
            error_type = type(error).__name__
            error_message = str(error)[:2000]

        trace = AIRequestTrace.objects.create(
            trace_id=trace_id,
            source=source,
            user=user,
            query_log=query_log,
            ai_task_run=ai_task_run,
            status=status,
            provider=llm_meta.get("provider", ""),
            model=llm_meta.get("model", ""),
            providers_attempted=llm_meta.get("providers_attempted", []),
            retry_count=llm_meta.get("retry_count", 0) or 0,
            prompt_tokens=llm_meta.get("prompt_tokens"),
            completion_tokens=llm_meta.get("completion_tokens"),
            total_tokens=llm_meta.get("total_tokens"),
            llm_latency_ms=llm_meta.get("latency_ms"),
            time_to_first_token_ms=llm_meta.get("time_to_first_token_ms"),
            retrieved_chunks=retrieved_chunks,
            citation_count=citation_count,
            cache_hit=cache_hit,
            stages=stages,
            total_duration_ms=duration,
            bottleneck_stage=bottleneck_stage,
            bottleneck_label=bottleneck_label,
            error_type=error_type,
            error_message=error_message,
        )

        return trace

    except Exception:
        logger.exception("observability_service.save_trace: failed to persist trace_id=%s source=%s", trace_id, source)
        return None


# ============================================================
# Read side - AI Logs page / Analytics Performance section
# ============================================================

def list_traces(filters: dict = None, page_size: int = 25, page: int = 1):
    """
    Filtered/paginated AIRequestTrace queryset for the AI Logs list
    view. `filters` (all optional): source, user_id, provider, model,
    status, error_type, date_from, date_to, trace_id (exact or partial).
    """

    filters = filters or {}
    qs = AIRequestTrace.objects.select_related("user", "query_log", "ai_task_run").all()

    if filters.get("source"):
        qs = qs.filter(source=filters["source"])
    if filters.get("user_id"):
        qs = qs.filter(user_id=filters["user_id"])
    if filters.get("provider"):
        qs = qs.filter(provider=filters["provider"])
    if filters.get("model"):
        qs = qs.filter(model=filters["model"])
    if filters.get("status"):
        qs = qs.filter(status=filters["status"])
    if filters.get("error_type"):
        qs = qs.filter(error_type=filters["error_type"])
    if filters.get("date_from"):
        qs = qs.filter(created_at__date__gte=filters["date_from"])
    if filters.get("date_to"):
        qs = qs.filter(created_at__date__lte=filters["date_to"])
    if filters.get("trace_id"):
        qs = qs.filter(trace_id__icontains=filters["trace_id"])

    total = qs.count()
    start = (page - 1) * page_size

    return {
        "results": list(qs[start:start + page_size]),
        "total": total,
        "page": page,
        "page_size": page_size,
        "num_pages": max(1, -(-total // page_size)),
    }


def get_trace_detail(trace_id: str) -> AIRequestTrace | None:
    return AIRequestTrace.objects.select_related("user", "query_log", "ai_task_run").filter(trace_id=trace_id).first()


def _apply_common_filters(qs, filters: dict):
    if filters.get("source"):
        qs = qs.filter(source=filters["source"])
    if filters.get("user_id"):
        qs = qs.filter(user_id=filters["user_id"])
    if filters.get("date_from"):
        qs = qs.filter(created_at__date__gte=filters["date_from"])
    if filters.get("date_to"):
        qs = qs.filter(created_at__date__lte=filters["date_to"])
    return qs


def get_performance_summary(filters: dict = None) -> dict:
    """
    Aggregate performance metrics for Analytics' "AI Performance"
    section. Returns {"has_data": False} rather than misleading zeros
    when there are no traces yet (e.g. right after this feature ships,
    before any traffic has flowed through it) or none match `filters`.

    `filters["user_id"]`, if given, scopes everything to one user's own
    requests/runs - RAG.views.analytics_view passes request.user.id for
    anyone without the "analytics.view_all" permission, matching
    get_analytics_data()'s existing per-user scoping for the rest of
    that page (a plain user was never meant to see every other user's
    aggregate LLM usage).
    """

    filters = filters or {}
    qs = _apply_common_filters(AIRequestTrace.objects.filter(status=AIRequestTrace.Status.COMPLETED), filters)

    if not qs.exists():
        return {"has_data": False}

    latency = qs.aggregate(
        avg=Avg("total_duration_ms"),
        p50=PercentileCont("total_duration_ms", 0.5),
        p95=PercentileCont("total_duration_ms", 0.95),
        p99=PercentileCont("total_duration_ms", 0.99),
    )

    all_qs = _apply_common_filters(AIRequestTrace.objects.all(), filters)

    total_requests = all_qs.count()
    failed_requests = all_qs.filter(status=AIRequestTrace.Status.FAILED).count()

    provider_stats = list(
        all_qs.exclude(provider="").values("provider").annotate(
            total=Count("id"),
            failures=Count("id", filter=Q(status=AIRequestTrace.Status.FAILED)),
        ).order_by("-total")
    )
    for row in provider_stats:
        row["success_rate"] = round((1 - row["failures"] / row["total"]) * 100, 1) if row["total"] else 0.0

    # providers_attempted is a JSON list - a fallback happened whenever
    # more than one provider was tried. len() isn't filterable directly
    # in the ORM across arbitrary Postgres JSON, so this is evaluated in
    # Python against the already-materialized "completed" queryset -
    # fine at this data volume (per-request rows, not per-token).
    fallback_used = sum(1 for t in qs.only("providers_attempted") if len(t.providers_attempted or []) > 1)

    cache_qs = qs.filter(source=AIRequestTrace.Source.ASK_AI, cache_hit__isnull=False)
    cache_total = cache_qs.count()
    cache_hits = cache_qs.filter(cache_hit=True).count()

    bottleneck_counts = list(
        qs.exclude(bottleneck_label="").values("bottleneck_label").annotate(count=Count("id")).order_by("-count")
    )

    error_breakdown = list(
        all_qs.exclude(error_type="").values("error_type").annotate(count=Count("id")).order_by("-count")[:10]
    )

    return {
        "has_data": True,
        "total_requests": total_requests,
        "completed_requests": qs.count(),
        "failed_requests": failed_requests,
        "success_rate": round((1 - failed_requests / total_requests) * 100, 1) if total_requests else 0.0,
        "avg_latency_ms": round(latency["avg"] or 0),
        "p50_latency_ms": round(latency["p50"] or 0),
        "p95_latency_ms": round(latency["p95"] or 0),
        "p99_latency_ms": round(latency["p99"] or 0),
        "provider_stats": provider_stats,
        "fallback_used": fallback_used,
        "fallback_rate": round((fallback_used / qs.count()) * 100, 1) if qs.count() else 0.0,
        "cache_hit_rate": round((cache_hits / cache_total) * 100, 1) if cache_total else None,
        "bottleneck_breakdown": bottleneck_counts,
        "error_breakdown": error_breakdown,
    }


def get_recent_provider_status(minutes: int = 15) -> dict:
    """
    {provider: {"ok": bool|None, "latency_ms": int|None, "message": str}}
    derived from real AIRequestTrace rows in the last `minutes` - the
    free, zero-API-cost alternative to LLMClient.health_check()'s live
    generate() call, used by health_service.py's auto-refresh path so
    leaving the Monitoring page open doesn't keep making real provider
    requests every 15 seconds (a manual "Check Now" still does the live
    call, on demand - see health_service.get_health_status()).

    A provider with zero requests in the window reports ok=None ("no
    recent data") rather than a guessed True/False - silence isn't the
    same as health, and this must never fabricate a status it hasn't
    actually observed.
    """

    from datetime import timedelta

    from django.db.models import Avg, Count, Q
    from django.utils import timezone

    since = timezone.now() - timedelta(minutes=minutes)

    rows = (
        AIRequestTrace.objects.filter(created_at__gte=since)
        .exclude(provider="")
        .values("provider")
        .annotate(
            total=Count("id"),
            failures=Count("id", filter=Q(status=AIRequestTrace.Status.FAILED)),
            avg_latency=Avg("llm_latency_ms"),
        )
    )

    results = {}

    for row in rows:
        succeeded = row["total"] - row["failures"]
        results[row["provider"]] = {
            "ok": succeeded > 0,
            "latency_ms": round(row["avg_latency"]) if row["avg_latency"] else None,
            "message": f"{succeeded}/{row['total']} succeeded in the last {minutes}m",
        }

    return results


def get_filter_options() -> dict:
    """Distinct provider/model/error_type values currently in AIRequestTrace, for populating the AI Logs page's filter dropdowns from real data rather than a hardcoded list."""

    return {
        "providers": list(
            AIRequestTrace.objects.exclude(provider="").values_list("provider", flat=True).distinct().order_by("provider")
        ),
        "models": list(
            AIRequestTrace.objects.exclude(model="").values_list("model", flat=True).distinct().order_by("model")
        ),
        "error_types": list(
            AIRequestTrace.objects.exclude(error_type="").values_list("error_type", flat=True).distinct().order_by("error_type")
        ),
    }
