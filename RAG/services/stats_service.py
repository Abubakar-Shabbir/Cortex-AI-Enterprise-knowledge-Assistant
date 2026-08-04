from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.db.models import Avg, Count, Sum
from django.utils import timezone

from ..models import ChunkEmbedding, Document, DocumentChunk, Entity, QueryLog
from ..utils.formatting import format_bytes, format_ms


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
    }


def get_recent_activity(user, limit=5):

    return {
        "recent_documents": Document.objects.filter(user=user).order_by("-uploaded_at")[:limit],
        "recent_questions": QueryLog.objects.filter(user=user).order_by("-created_at")[:limit],
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

    top_entity = Entity.objects.filter(user=user).order_by("-mention_count").first()
    if top_entity:
        recommendations.append({
            "icon": "sparkles",
            "title": f'Try asking about "{top_entity.display_name}"',
            "description": f"It's the most frequently mentioned entity across your documents ({top_entity.mention_count} mentions).",
            "action_url_name": "ask_ai",
            "action_label": "Ask now",
        })

    return {
        "insights": insights[:3],
        "recommendations": recommendations[:3],
    }


def get_analytics_data(user, days=14):
    """
    Aggregates built entirely from real Document
    and QueryLog rows - no synthetic data.
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

    labels, questions_series, uploads_series = [], [], []
    confidence_series, response_time_series = [], []

    for i in range(days):
        day = start_date + timedelta(days=i)
        labels.append(day.strftime("%b %d"))
        questions_series.append(questions_by_day.get(day, 0))
        uploads_series.append(uploads_by_day.get(day, 0))

        day_confidences = confidence_by_day.get(day, [])
        day_response_times = response_time_by_day.get(day, [])
        confidence_series.append(round(sum(day_confidences) / len(day_confidences)) if day_confidences else None)
        response_time_series.append(round(sum(day_response_times) / len(day_response_times)) if day_response_times else None)

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
        "avg_response_time": format_ms(round(avg_response)),
        "total_storage": format_bytes(sum(storage_by_type.values())),
    }


def get_system_status():
    """
    Live, cheap infrastructure checks - a real
    SELECT 1 and a pg_extension lookup, plus
    configuration values already in settings.py.
    No external API calls are made here.
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
    total_storage = Document.objects.aggregate(total=Sum("file_size"))["total"] or 0

    return {
        "db_online": db_online,
        "pgvector_enabled": pgvector_enabled,
        "embedding_model": settings.EMBEDDING_MODEL,
        "embedding_dimension": settings.EMBEDDING_DIMENSION,
        "llm_model": settings.LLM_MODEL,
        "llm_configured": bool(settings.GEMINI_API_KEY),
        "total_documents": Document.objects.count(),
        "total_chunks": total_chunks,
        "total_embeddings": total_embeddings,
        "embeddings_complete": total_chunks == total_embeddings,
        "total_storage": format_bytes(total_storage),
    }
