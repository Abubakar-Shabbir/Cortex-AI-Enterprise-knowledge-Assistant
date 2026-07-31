from collections import Counter, defaultdict
from datetime import timedelta

from django.conf import settings
from django.db import connection
from django.db.models import Avg, Sum
from django.utils import timezone

from ..models import ChunkEmbedding, Document, DocumentChunk, QueryLog
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


def get_analytics_data(user, days=14):
    """
    Aggregates built entirely from real Document
    and QueryLog rows - no synthetic data.
    """

    today = timezone.localdate()
    start_date = today - timedelta(days=days - 1)

    questions_by_day = Counter()

    for created_at in QueryLog.objects.filter(
        user=user, created_at__date__gte=start_date
    ).values_list("created_at", flat=True):
        questions_by_day[timezone.localtime(created_at).date()] += 1

    uploads_by_day = Counter()

    for uploaded_at in Document.objects.filter(
        user=user, uploaded_at__date__gte=start_date
    ).values_list("uploaded_at", flat=True):
        uploads_by_day[timezone.localtime(uploaded_at).date()] += 1

    labels, questions_series, uploads_series = [], [], []

    for i in range(days):
        day = start_date + timedelta(days=i)
        labels.append(day.strftime("%b %d"))
        questions_series.append(questions_by_day.get(day, 0))
        uploads_series.append(uploads_by_day.get(day, 0))

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
