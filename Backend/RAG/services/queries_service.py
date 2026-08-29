"""
Admin > Queries - workspace-wide query log search/filter/sort and
analytics.

Privacy boundary: everything in this module operates on QueryLog rows
belonging to every user (that's the point of the page - see
RAG.services.permission_service's "queries.view_all_logs" /
"queries.view_content" split), but never returns the raw `question`/
`answer`/`sources` text itself. Status ("Answered" vs "No Answer
Found") is derived server-side from `answer` via
prompt_templates.is_not_found_answer() - a boolean the caller can show
to any "queries.view_all_logs" holder without exposing the content
that produced it. The view layer (RAG.views.admin_queries_view /
admin_query_detail_view) is solely responsible for gating the actual
content behind "queries.view_content".
"""

from django.db.models import Avg, Count, Q

from ..models import QueryLog
from .prompt_templates import is_not_found_answer

SORT_OPTIONS = {
    "newest": "-created_at",
    "oldest": "created_at",
    "confidence_high": "-confidence",
    "confidence_low": "confidence",
    "slowest": "-response_time_ms",
    "fastest": "response_time_ms",
}

DEFAULT_SORT = "newest"


def get_search_methods():
    """Distinct search_method values currently in use, for the filter dropdown."""

    return list(
        QueryLog.objects.order_by("search_method")
        .values_list("search_method", flat=True)
        .distinct()
    )


def filter_and_sort_queries(params, request_user=None):
    """
    Build the QueryLog queryset for Admin > Queries from a request's
    GET params. Every filter is metadata-only (scope, owner username,
    search method, confidence range, date range, status, flagged) -
    the one exception, `q`, matches against `question`/`answer` text
    via the database and is the caller's responsibility to only wire
    up when the actor holds "queries.view_content" (see
    RAG.views.admin_queries_view).

    `scope` splits the workspace-wide list along the one axis every
    viewer can always tell apart regardless of "queries.view_content" -
    whose account a query belongs to - without ever touching question/
    answer content: "mine" is the viewing admin's own queries (they
    already know their own questions), "others" is everyone else's.
    Requires `request_user` for "mine"/"others" to mean anything.
    """

    logs = QueryLog.objects.select_related("user").all()

    scope = params.get("scope", "").strip()
    if scope == "mine" and request_user is not None:
        logs = logs.filter(user=request_user)
    elif scope == "others" and request_user is not None:
        logs = logs.exclude(user=request_user)

    owner = params.get("owner", "").strip()
    if owner:
        logs = logs.filter(user__username__icontains=owner)

    method = params.get("method", "").strip()
    if method:
        logs = logs.filter(search_method=method)

    status = params.get("status", "").strip()
    if status == "answered":
        logs = logs.exclude(answer__icontains="couldn't find the answer")
    elif status == "not_found":
        logs = logs.filter(answer__icontains="couldn't find the answer")

    min_confidence = params.get("min_confidence", "").strip()
    if min_confidence.isdigit():
        logs = logs.filter(confidence__gte=int(min_confidence))

    date_from = params.get("date_from", "").strip()
    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)

    date_to = params.get("date_to", "").strip()
    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)

    if params.get("flagged") == "1":
        logs = logs.filter(is_flagged=True)

    content_query = params.get("q", "").strip()
    if content_query and params.get("_content_search_allowed"):
        logs = logs.filter(Q(question__icontains=content_query) | Q(answer__icontains=content_query))

    sort = params.get("sort", DEFAULT_SORT)
    logs = logs.order_by(SORT_OPTIONS.get(sort, SORT_OPTIONS[DEFAULT_SORT]))

    return logs


def get_queries_analytics(logs_queryset):
    """
    Workspace-wide query analytics for the summary cards atop
    Admin > Queries - derived entirely from metadata/aggregates, safe
    for any "queries.view_all_logs" holder.
    """

    counts = logs_queryset.aggregate(
        total=Count("id"),
        not_found=Count("id", filter=Q(answer__icontains="couldn't find the answer")),
        flagged_count=Count("id", filter=Q(is_flagged=True)),
        avg_confidence=Avg("confidence"),
        avg_response_time=Avg("response_time_ms"),
    )

    total = counts["total"]

    if total == 0:
        return {
            "total": 0,
            "answered_pct": 0,
            "avg_confidence": 0,
            "avg_response_time": 0,
            "flagged_count": 0,
            "top_method": "—",
        }

    answered_pct = round(((total - counts["not_found"]) / total) * 100)
    flagged_count = counts["flagged_count"]

    top_method_row = (
        logs_queryset.values("search_method")
        .annotate(count=Count("id"))
        .order_by("-count")
        .first()
    )

    return {
        "total": total,
        "answered_pct": answered_pct,
        "avg_confidence": round(counts["avg_confidence"] or 0),
        "avg_response_time": round(counts["avg_response_time"] or 0),
        "flagged_count": flagged_count,
        "top_method": top_method_row["search_method"] if top_method_row else "—",
    }


def annotate_status(logs):
    """
    Attach a `.status_label`/`.status_answered` pair to each log in
    `logs` (a list, not a queryset - call after slicing/pagination) -
    the template-facing form of is_not_found_answer(), computed
    server-side so the template never touches raw answer text for
    viewers who lack "queries.view_content".
    """

    for log in logs:
        not_found = is_not_found_answer(log.answer)
        log.status_answered = not not_found
        log.status_label = "No Answer Found" if not_found else "Answered"

    return logs
