from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from ..models import ActivityLog, AITaskRun, ChunkEmbedding, Document, DocumentChunk, QueryLog
from ..utils.formatting import format_bytes, format_ms
from .knowledge_service import get_knowledge_overview, search_topics


def get_dashboard_stats(user):
    """
    Real aggregate numbers for the dashboard
    stat cards, scoped to the current user.
    """

    documents = Document.objects.filter(user=user)
    logs = QueryLog.objects.filter(user=user)

    today = timezone.localdate()

    avg_response = logs.aggregate(avg=Avg("response_time_ms"))["avg"] or 0
    storage_bytes = documents.aggregate(total=Sum("file_size"))["total"] or 0

    return {
        "total_documents": documents.count(),
        "total_chunks": DocumentChunk.objects.filter(document__user=user).count(),
        "questions_asked": logs.count(),
        "today_queries": logs.filter(created_at__date=today).count(),
        "avg_response_time": format_ms(round(avg_response)),
        "storage_used": format_bytes(storage_bytes),
        "last_upload": documents.order_by("-uploaded_at").first(),
        "ai_task_runs": AITaskRun.objects.filter(user=user).count(),
    }


def get_recent_activity(user, limit=5):

    return {
        "recent_documents": Document.objects.filter(user=user).order_by("-uploaded_at")[:limit],
        "recent_questions": QueryLog.objects.filter(user=user).order_by("-created_at")[:limit],
        "recent_ai_task_runs": AITaskRun.objects.filter(user=user).order_by("-created_at")[:limit],
    }


def get_activity_summary(user):
    """
    Real per-user activity totals for the Profile module (self and
    Admin User Management views) - every number is a live count against
    that user's own rows, nothing cached or estimated.
    """

    return {
        "documents_owned": Document.objects.filter(user=user).count(),
        "queries_asked": QueryLog.objects.filter(user=user).count(),
        "ai_task_runs": AITaskRun.objects.filter(user=user).count(),
        "activity_events": ActivityLog.objects.filter(actor=user).count(),
        "account_age_days": (timezone.now() - user.date_joined).days,
    }


def get_dashboard_insights(user):
    """
    Smart Insights / Recommendations for the dashboard - a handful of
    computed-not-fabricated observations from the user's own
    Document/QueryLog/Entity data. Nothing here is LLM-generated or
    sampled; every number is a real aggregate, and a card is only
    included when there's real data behind it.
    """

    documents = Document.objects.filter(user=user)
    logs = QueryLog.objects.filter(user=user)

    insights = []
    recommendations = []

    avg_confidence = logs.aggregate(avg=Avg("confidence"))["avg"]
    if avg_confidence is not None:
        insights.append({
            "icon": "gauge",
            "title": f"{round(avg_confidence)}% average confidence",
            "description": "Across every answer you've received so far.",
        })

    since = timezone.now() - timedelta(days=30)
    day_counts = Counter(
        timezone.localtime(created_at).strftime("%A")
        for created_at in logs.filter(created_at__gte=since).values_list("created_at", flat=True)
    )
    if day_counts:
        busiest_day, count = day_counts.most_common(1)[0]
        insights.append({
            "icon": "calendar-days",
            "title": f"{busiest_day} is your busiest day",
            "description": f"{count} question{'s' if count != 1 else ''} asked on {busiest_day}s in the last 30 days.",
        })

    top_method = (
        logs.exclude(search_method="")
        .values("search_method")
        .annotate(count=Count("id"))
        .order_by("-count")
        .first()
    )
    if top_method:
        insights.append({
            "icon": "route",
            "title": top_method["search_method"],
            "description": "Your most frequently used retrieval method.",
        })

    processing = documents.filter(chunk_count=0).count()
    if processing:
        recommendations.append({
            "icon": "loader-circle",
            "title": f"{processing} document{'s' if processing != 1 else ''} still processing",
            "description": "Chunking and embedding run in the background - check back shortly.",
            "action_url_name": "documents",
            "action_label": "View documents",
        })

    if documents.count() == 0:
        recommendations.append({
            "icon": "upload-cloud",
            "title": "Upload your first document",
            "description": "Once you upload a document, you can start asking questions about it.",
            "action_url_name": "documents",
            "action_label": "Go to Documents",
        })
    elif logs.count() == 0:
        recommendations.append({
            "icon": "message-square",
            "title": "Ask your first question",
            "description": "Your documents are ready - try asking the assistant something about them.",
            "action_url_name": "ask_ai",
            "action_label": "Go to AI Search",
        })

    # Reuses knowledge_service's Topic-merge (not a raw Entity.objects
    # filter by user=user) so this recommendation reflects everything
    # accessible to the viewer - owned, Organization Library, and
    # shared-with-them documents - not just ones they personally
    # uploaded. See the Knowledge Center's scoping-fix for why
    # Entity.user alone under-represents what a user can actually see.
    top_topics = search_topics(user, page=1)
    top_topic = top_topics.object_list[0] if top_topics.object_list else None
    if top_topic:
        recommendations.append({
            "icon": "sparkles",
            "title": f'Try asking about "{top_topic["display_name"]}"',
            "description": f"It's the most frequently mentioned topic across everything you can access ({top_topic['mention_count']} mentions).",
            "action_url_name": "ask_ai",
            "action_label": "Ask now",
        })

    return {
        "insights": insights[:3],
        "recommendations": recommendations[:3],
    }


def get_analytics_data(user, days=14, knowledge_overview=None):
    """
    Aggregates built entirely from real Document
    and QueryLog rows - no synthetic data.

    `knowledge_overview`, when provided, is used as-is instead of
    calling get_knowledge_overview(user) again - lets a caller that
    already needs the full overview dict for its own purposes (e.g.
    admin_dashboard_view, which also renders it directly) compute it
    once and share it here instead of rebuilding the same topic
    dataset twice per page load.
    """

    today = timezone.localdate()
    start_date = today - timedelta(days=days - 1)

    questions_by_day = Counter()
    confidence_by_day = defaultdict(list)
    response_time_by_day = defaultdict(list)

    for created_at, confidence, response_time_ms in QueryLog.objects.filter(
        user=user, created_at__date__gte=start_date
    ).values_list("created_at", "confidence", "response_time_ms"):
        day = timezone.localtime(created_at).date()
        questions_by_day[day] += 1
        confidence_by_day[day].append(confidence)
        response_time_by_day[day].append(response_time_ms)

    uploads_by_day = Counter()

    for uploaded_at in Document.objects.filter(
        user=user, uploaded_at__date__gte=start_date
    ).values_list("uploaded_at", flat=True):
        uploads_by_day[timezone.localtime(uploaded_at).date()] += 1

    ai_tasks_by_day = Counter()
    ai_task_status_counts = Counter()

    for created_at, status in AITaskRun.objects.filter(
        user=user, created_at__date__gte=start_date
    ).values_list("created_at", "status"):
        ai_tasks_by_day[timezone.localtime(created_at).date()] += 1
        ai_task_status_counts[status] += 1

    labels, questions_series, uploads_series = [], [], []
    confidence_series, response_time_series = [], []
    ai_task_runs_series = []

    for i in range(days):
        day = start_date + timedelta(days=i)
        labels.append(day.strftime("%b %d"))
        questions_series.append(questions_by_day.get(day, 0))
        uploads_series.append(uploads_by_day.get(day, 0))
        ai_task_runs_series.append(ai_tasks_by_day.get(day, 0))

        day_confidences = confidence_by_day.get(day, [])
        day_response_times = response_time_by_day.get(day, [])
        confidence_series.append(round(sum(day_confidences) / len(day_confidences)) if day_confidences else None)
        response_time_series.append(round(sum(day_response_times) / len(day_response_times)) if day_response_times else None)

    ai_task_status_display = dict(AITaskRun.Status.choices)
    ai_task_status_labels = [ai_task_status_display.get(s, s) for s in ai_task_status_counts] or ["No runs yet"]
    ai_task_status_values = list(ai_task_status_counts.values()) or [0]

    if knowledge_overview is None:
        knowledge_overview = get_knowledge_overview(user)

    top_docs = Document.objects.filter(user=user).order_by("-chunk_count")[:8]

    search_type_counts = Counter()

    for source_list in QueryLog.objects.filter(user=user).values_list("sources", flat=True):
        for source in source_list or []:
            search_type_counts[source.get("search_type", "unknown")] += 1

    storage_by_type = defaultdict(int)

    for file_type, file_size in Document.objects.filter(user=user).values_list(
        "file_type", "file_size"
    ):
        storage_by_type[(file_type or "other").upper()] += file_size or 0

    avg_response = QueryLog.objects.filter(user=user).aggregate(
        avg=Avg("response_time_ms")
    )["avg"] or 0

    # Confidence Distribution - every answered question bucketed by
    # confidence tier, matching the same thresholds ask_ai.html colors
    # its confidence pill by (>=70 success, >=40 warning, else danger),
    # just split into 4 readable bands here instead of 3.
    confidence_buckets = [
        ("Excellent (80-100%)", 80, 101, "#1F7A4D"),
        ("Good (60-79%)", 60, 80, "#2A78D6"),
        ("Fair (40-59%)", 40, 60, "#C77700"),
        ("Low (0-39%)", 0, 40, "#C62828"),
    ]
    all_confidences = list(
        QueryLog.objects.filter(user=user).values_list("confidence", flat=True)
    )
    confidence_distribution_labels = []
    confidence_distribution_values = []
    confidence_distribution_colors = []
    for label, low, high, color in confidence_buckets:
        count = sum(1 for c in all_confidences if low <= c < high)
        confidence_distribution_labels.append(label)
        confidence_distribution_values.append(count)
        confidence_distribution_colors.append(color)

    # Weekday Activity - question volume by day of week, over a longer
    # 90-day window (independent of `days`) since a meaningful "which
    # weekday are you busiest" pattern needs more than a 2-week sample.
    weekday_window_start = today - timedelta(days=89)
    weekday_labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    weekday_counts = [0] * 7
    for created_at in QueryLog.objects.filter(
        user=user, created_at__date__gte=weekday_window_start
    ).values_list("created_at", flat=True):
        weekday_counts[timezone.localtime(created_at).weekday()] += 1

    return {
        "labels": labels,
        "questions_series": questions_series,
        "uploads_series": uploads_series,
        "confidence_series": confidence_series,
        "response_time_series": response_time_series,
        "chunk_labels": [doc.title[:22] for doc in top_docs],
        "chunk_values": [doc.chunk_count for doc in top_docs],
        "search_type_labels": list(search_type_counts.keys()) or ["No queries yet"],
        "search_type_values": list(search_type_counts.values()) or [0],
        "storage_type_labels": list(storage_by_type.keys()) or ["No documents yet"],
        "storage_type_values": list(storage_by_type.values()) or [0],
        "confidence_distribution_labels": confidence_distribution_labels,
        "confidence_distribution_values": confidence_distribution_values,
        "confidence_distribution_colors": confidence_distribution_colors,
        "weekday_labels": weekday_labels,
        "weekday_values": weekday_counts,
        "total_questions": sum(questions_series),
        "total_uploads": sum(uploads_series),
        "avg_response_time": format_ms(round(avg_response)),
        "total_storage": format_bytes(sum(storage_by_type.values())),
        "ai_task_runs_series": ai_task_runs_series,
        "total_ai_task_runs": sum(ai_task_runs_series),
        "ai_task_status_labels": ai_task_status_labels,
        "ai_task_status_values": ai_task_status_values,
        "total_topics": knowledge_overview["total_entities"],
        "total_relationships": knowledge_overview["total_relationships"],
    }


def get_comparison_report_data(user, days=14):
    """
    Period-over-period comparison (the last `days` days vs. the
    `days` immediately before that) across the headline usage metrics
    - backs the Reports page's Comparative Report. Every figure is a
    live aggregate over the user's own Document/QueryLog rows, reusing
    the same _period_change() helper get_kpi_trends() already uses for
    the Dashboard's trend badges, just over a configurable window
    instead of a fixed 7 days.
    """

    today = timezone.localdate()
    current_start = today - timedelta(days=days - 1)
    previous_start = current_start - timedelta(days=days)
    previous_end = current_start - timedelta(days=1)

    documents_qs = Document.objects.filter(user=user)
    logs_qs = QueryLog.objects.filter(user=user)
    ai_tasks_qs = AITaskRun.objects.filter(user=user)

    current_documents = documents_qs.filter(uploaded_at__date__gte=current_start)
    previous_documents = documents_qs.filter(uploaded_at__date__range=(previous_start, previous_end))

    current_logs = logs_qs.filter(created_at__date__gte=current_start)
    previous_logs = logs_qs.filter(created_at__date__range=(previous_start, previous_end))

    current_ai_tasks = ai_tasks_qs.filter(created_at__date__gte=current_start)
    previous_ai_tasks = ai_tasks_qs.filter(created_at__date__range=(previous_start, previous_end))

    current_avg_confidence = current_logs.aggregate(avg=Avg("confidence"))["avg"] or 0
    previous_avg_confidence = previous_logs.aggregate(avg=Avg("confidence"))["avg"] or 0

    current_avg_response = current_logs.aggregate(avg=Avg("response_time_ms"))["avg"] or 0
    previous_avg_response = previous_logs.aggregate(avg=Avg("response_time_ms"))["avg"] or 0

    current_storage = current_documents.aggregate(total=Sum("file_size"))["total"] or 0
    previous_storage = previous_documents.aggregate(total=Sum("file_size"))["total"] or 0

    def row(label, current, previous, formatter=round):
        change_pct, direction = _period_change(current, previous)
        return {
            "label": label,
            "current": formatter(current),
            "previous": formatter(previous),
            "change_pct": change_pct,
            "direction": direction,
            # Clamped to 100 for the Reports page's delta bar - the bar
            # visualizes magnitude, not the literal (possibly 4-digit)
            # percent, which would otherwise overflow its track.
            "bar_width": min(abs(change_pct), 100),
        }

    rows = [
        row("Documents Uploaded", current_documents.count(), previous_documents.count()),
        row("Questions Asked", current_logs.count(), previous_logs.count()),
        row("Avg Confidence (%)", round(current_avg_confidence), round(previous_avg_confidence)),
        row("Avg Response Time (ms)", round(current_avg_response), round(previous_avg_response)),
        row("Storage Added", current_storage, previous_storage, format_bytes),
        row("AI Task Runs", current_ai_tasks.count(), previous_ai_tasks.count()),
    ]

    return {
        "days": days,
        "current_range": f"{current_start.strftime('%b %d')} – {today.strftime('%b %d')}",
        "previous_range": f"{previous_start.strftime('%b %d')} – {previous_end.strftime('%b %d')}",
        "rows": rows,
    }


def get_system_status(minimal=False):
    """
    Live, cheap infrastructure checks - a real
    SELECT 1 and a pg_extension lookup, plus
    configuration values already in settings.py.
    No external API calls are made here.

    `minimal=True` (used by health_service._check_database(), which
    backs the public /health/ endpoint) skips every query this
    function's callers don't actually need for a liveness check -
    total_documents/total_storage and the LLM-provider config lookup
    exist only for settings_view's full dashboard. Polled repeatedly by
    Railway (and any orchestrator) during every deploy, so shaving
    unnecessary DB round trips off this path directly helps the health
    check "return quickly" instead of accumulating latency query by
    query on every poll.
    """

    db_online = False
    pgvector_enabled = False

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            db_online = cursor.fetchone() == (1,)

            cursor.execute(
                "SELECT EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector')"
            )
            pgvector_enabled = bool(cursor.fetchone()[0])

    except Exception:
        db_online = False
        pgvector_enabled = False

    total_chunks = DocumentChunk.objects.count()
    total_embeddings = ChunkEmbedding.objects.count()

    if minimal:
        return {
            "db_online": db_online,
            "pgvector_enabled": pgvector_enabled,
            "embedding_model": settings.EMBEDDING_MODEL,
            "embedding_dimension": settings.EMBEDDING_DIMENSION,
            "total_chunks": total_chunks,
            "total_embeddings": total_embeddings,
            "embeddings_complete": total_chunks == total_embeddings,
        }

    total_storage = Document.objects.aggregate(total=Sum("file_size"))["total"] or 0

    # LLM_PROVIDER selects which key/model actually matters - checking
    # GEMINI_API_KEY unconditionally would report "not configured" for a
    # workspace correctly running on OpenRouter or Groq, and vice versa.
    # Looked up generically via llm_client.PROVIDER_REGISTRY (the same
    # single source of truth the fallback chain/Settings page/health
    # checks already use) rather than a hardcoded if/else - the
    # if/else this replaced only ever branched openrouter-vs-Gemini and
    # silently mis-checked GEMINI_API_KEY/LLM_MODEL for a Groq-primary
    # workspace.
    from .llm_client import PROVIDER_REGISTRY

    llm_provider = settings.LLM_PROVIDER.lower()
    provider_meta = PROVIDER_REGISTRY.get(llm_provider)

    if provider_meta:
        llm_model = getattr(settings, provider_meta["model_setting"], "")
        llm_configured = bool(getattr(settings, provider_meta["api_key_setting"], ""))
    else:
        llm_model = ""
        llm_configured = False

    return {
        "db_online": db_online,
        "pgvector_enabled": pgvector_enabled,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dimension": settings.EMBEDDING_DIMENSION,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_configured": llm_configured,
        "total_documents": Document.objects.count(),
        "total_chunks": total_chunks,
        "total_embeddings": total_embeddings,
        "embeddings_complete": total_chunks == total_embeddings,
        "total_storage": format_bytes(total_storage),
    }


# ============================================================
# Admin Dashboard (Sprint 11)
# ============================================================
#
# Everything below backs the redesigned Dashboard page: KPI trend
# badges/sparklines, the "Documents Over Time" chart, the "Document
# Types" donut, and the Recent Documents table. All figures are real
# aggregates over the requesting user's own Document/DocumentChunk/
# QueryLog rows - nothing here is sampled or fabricated.

DOCUMENT_TYPE_COLORS = {
    "PDF": "#8B1E2D",
    "DOCX": "#C77700",
    "TXT": "#1F7A4D",
}
DOCUMENT_TYPE_OTHER_COLOR = "#A9989A"


def get_document_type_breakdown(user):
    """
    Document count by file type, for the Document Types donut chart.
    Anything outside PDF/DOCX/TXT collapses into "Other" so the chart
    stays readable regardless of how many distinct extensions a user
    has uploaded.
    """

    counts = Counter(
        (file_type or "OTHER").upper()
        for file_type in Document.objects.filter(user=user).values_list("file_type", flat=True)
    )

    known_types = ["PDF", "DOCX", "TXT"]
    other_count = sum(count for file_type, count in counts.items() if file_type not in known_types)

    breakdown = [
        {"type": file_type, "count": counts[file_type], "color": DOCUMENT_TYPE_COLORS[file_type]}
        for file_type in known_types
        if counts.get(file_type, 0) > 0
    ]

    if other_count:
        breakdown.append({"type": "Other", "count": other_count, "color": DOCUMENT_TYPE_OTHER_COLOR})

    total = sum(item["count"] for item in breakdown)

    for item in breakdown:
        item["percent"] = round((item["count"] / total) * 100) if total else 0

    return {"breakdown": breakdown, "total": total}


def get_documents_over_time(user, days=7):
    """
    Two aligned series for the "Documents Over Time" chart, over the
    last `days` days: `series` is the cumulative running total
    (workspace growth, the line) and `daily` is same-day new uploads
    (the bar overlay) - both derived from one query (`daily_counts`),
    so plotting both costs nothing extra over the line alone.
    """

    today = timezone.localdate()
    start_date = today - timedelta(days=days - 1)

    running_total = Document.objects.filter(user=user, uploaded_at__date__lt=start_date).count()

    daily_counts = Counter(
        timezone.localtime(uploaded_at).date()
        for uploaded_at in Document.objects.filter(
            user=user, uploaded_at__date__gte=start_date
        ).values_list("uploaded_at", flat=True)
    )

    labels, series, daily = [], [], []

    for i in range(days):
        day = start_date + timedelta(days=i)
        added = daily_counts.get(day, 0)
        running_total += added
        labels.append(day.strftime("%b %d"))
        series.append(running_total)
        daily.append(added)

    return {"labels": labels, "series": series, "daily": daily}


def _period_change(current, previous):
    """
    Percent change and direction between two period totals, guarding
    the divide-by-zero case where the prior period had nothing to
    compare against.
    """

    if previous == 0:
        return (100.0 if current > 0 else 0.0), ("up" if current > 0 else "flat")

    pct = ((current - previous) / previous) * 100

    return round(pct, 1), ("up" if pct >= 0 else "down")


def get_kpi_trends(user):
    """
    Trend badge (% change vs. the prior period) and a 7-point daily
    sparkline for each Dashboard KPI card. Documents/Chunks/Storage
    compare the last 7 days against the 7 days before that; Queries
    compares today against yesterday - matching the "vs" label shown
    next to each figure on the card.
    """

    today = timezone.localdate()
    window_start = today - timedelta(days=6)
    prior_start = window_start - timedelta(days=7)
    prior_end = window_start - timedelta(days=1)

    def daily_counts(queryset, date_field):
        counts = Counter(
            timezone.localtime(value).date()
            for value in queryset.values_list(date_field, flat=True)
        )
        return [counts.get(window_start + timedelta(days=i), 0) for i in range(7)]

    def daily_sum(queryset, date_field, value_field):
        totals = defaultdict(int)
        for date_value, amount in queryset.values_list(date_field, value_field):
            totals[timezone.localtime(date_value).date()] += amount or 0
        return [totals.get(window_start + timedelta(days=i), 0) for i in range(7)]

    documents_qs = Document.objects.filter(user=user)
    chunks_qs = DocumentChunk.objects.filter(document__user=user)
    logs_qs = QueryLog.objects.filter(user=user)
    ai_tasks_qs = AITaskRun.objects.filter(user=user)

    recent_documents = documents_qs.filter(uploaded_at__date__gte=window_start)
    recent_chunks = chunks_qs.filter(created_at__date__gte=window_start)
    recent_logs = logs_qs.filter(created_at__date__gte=window_start)
    recent_ai_tasks = ai_tasks_qs.filter(created_at__date__gte=window_start)

    documents_current = recent_documents.count()
    documents_previous = documents_qs.filter(uploaded_at__date__range=(prior_start, prior_end)).count()

    chunks_current = recent_chunks.count()
    chunks_previous = chunks_qs.filter(created_at__date__range=(prior_start, prior_end)).count()

    storage_current = recent_documents.aggregate(total=Sum("file_size"))["total"] or 0
    storage_previous = documents_qs.filter(
        uploaded_at__date__range=(prior_start, prior_end)
    ).aggregate(total=Sum("file_size"))["total"] or 0

    queries_today = logs_qs.filter(created_at__date=today).count()
    queries_yesterday = logs_qs.filter(created_at__date=today - timedelta(days=1)).count()

    ai_tasks_current = recent_ai_tasks.count()
    ai_tasks_previous = ai_tasks_qs.filter(created_at__date__range=(prior_start, prior_end)).count()

    doc_pct, doc_dir = _period_change(documents_current, documents_previous)
    chunk_pct, chunk_dir = _period_change(chunks_current, chunks_previous)
    storage_pct, storage_dir = _period_change(storage_current, storage_previous)
    query_pct, query_dir = _period_change(queries_today, queries_yesterday)
    ai_tasks_pct, ai_tasks_dir = _period_change(ai_tasks_current, ai_tasks_previous)

    documents_sparkline = daily_counts(recent_documents, "uploaded_at")
    chunks_sparkline = daily_counts(recent_chunks, "created_at")
    storage_sparkline = daily_sum(recent_documents, "uploaded_at", "file_size")
    ai_tasks_sparkline = daily_counts(recent_ai_tasks, "created_at")
    queries_sparkline = daily_counts(recent_logs, "created_at")

    return {
        "documents": {
            "change_pct": doc_pct, "direction": doc_dir,
            "sparkline": documents_sparkline, "has_activity": any(documents_sparkline),
        },
        "chunks": {
            "change_pct": chunk_pct, "direction": chunk_dir,
            "sparkline": chunks_sparkline, "has_activity": any(chunks_sparkline),
        },
        "storage": {
            "change_pct": storage_pct, "direction": storage_dir,
            "sparkline": storage_sparkline, "has_activity": any(storage_sparkline),
        },
        "ai_tasks": {
            "change_pct": ai_tasks_pct, "direction": ai_tasks_dir,
            "sparkline": ai_tasks_sparkline, "has_activity": any(ai_tasks_sparkline),
        },
        "queries": {
            "change_pct": query_pct, "direction": query_dir,
            "sparkline": queries_sparkline, "has_activity": any(queries_sparkline),
        },
    }


def get_recent_documents_table(user, limit=6):
    """
    Recent documents with per-row status/size/owner, for the Dashboard's
    Recent Documents table. Status mirrors the same chunk_count-vs-
    embedded-count calculation documents_view uses on the Documents
    page, so the two pages never disagree about a document's state.
    """

    documents = (
        Document.objects.filter(user=user)
        .annotate(embedded_chunks=Count("chunks__vector"))
        .order_by("-uploaded_at")[:limit]
    )

    # Single-tenant per user: every document on this page belongs to
    # the requesting user, so "Owner" is always them. There is no
    # multi-user workspace/admin view backing a cross-user table.
    owner_name = user.get_full_name() or user.username

    rows = []

    for doc in documents:

        if doc.chunk_count == 0:
            status = "Processing"
        elif doc.embedded_chunks >= doc.chunk_count:
            status = "Processed"
        else:
            status = "Partial"

        rows.append({
            "id": doc.id,
            "title": doc.title,
            "owner": owner_name,
            "file_type": (doc.file_type or "—").upper(),
            "chunk_count": doc.chunk_count,
            "size": format_bytes(doc.file_size),
            "size_bytes": doc.file_size,
            "uploaded_at": doc.uploaded_at,
            "status": status,
        })

    return rows
