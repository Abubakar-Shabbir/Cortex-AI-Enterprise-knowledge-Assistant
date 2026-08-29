"""
User Overview (/dashboard/) and Admin Overview (/admin/) as JSON -
reuses exactly the same service calls their Django-template
predecessors (RAG.views.user_dashboard / RAG.views.admin_dashboard_view)
already make. No aggregate query is reimplemented here.
"""

from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..services.knowledge_service import get_knowledge_overview
from ..services.permission_service import get_user_access_snapshot
from ..services.stats_service import (
    get_dashboard_stats,
    get_document_type_breakdown,
    get_documents_over_time,
    get_kpi_trends,
    get_recent_activity,
    get_recent_documents_table,
    get_system_status,
)
from .permissions import HasAdminAreaAccess

# Mirrors RAG.views.DASHBOARD_CHART_RANGES - the "Documents Over Time"
# chart's `?range=` control on Admin Overview.
DASHBOARD_CHART_RANGES = (7, 14, 30)


@api_view(["GET"])
def dashboard_view(request):
    user = request.user
    stats = get_dashboard_stats(user)
    activity = get_recent_activity(user)
    knowledge_overview = get_knowledge_overview(user)
    role, can_view_admin_area, user_permissions = get_user_access_snapshot(user)

    # Same merged-and-sorted shape context_processors.sidebar_status
    # builds for the sidebar/topbar - reusing the recent_documents/
    # recent_questions already fetched above instead of re-querying,
    # since user_dashboard.html's Activity Feed card renders that same
    # global context var.
    events = [
        {"icon": "file-up", "text": f'"{doc.title}" uploaded', "at": doc.uploaded_at}
        for doc in activity["recent_documents"]
    ] + [
        {"icon": "message-square", "text": f'Asked: "{log.question[:60]}"', "at": log.created_at}
        for log in activity["recent_questions"]
    ]
    events.sort(key=lambda e: e["at"], reverse=True)

    return Response({
        "stats": {
            "total_documents": stats["total_documents"],
            "total_chunks": stats["total_chunks"],
            "questions_asked": stats["questions_asked"],
            "today_queries": stats["today_queries"],
            "avg_response_time": stats["avg_response_time"],
            "storage_used": stats["storage_used"],
            "ai_task_runs": stats["ai_task_runs"],
        },
        "knowledge_overview": {
            "total_entities": knowledge_overview.get("total_entities", 0),
            "total_relationships": knowledge_overview.get("total_relationships", 0),
            "total_sources": knowledge_overview.get("total_sources", 0),
        },
        "recent_documents": [
            {
                "id": doc.id,
                "title": doc.title,
                "file_type": doc.file_type,
                "chunk_count": doc.chunk_count,
                "uploaded_at": doc.uploaded_at.isoformat(),
            }
            for doc in activity["recent_documents"]
        ],
        "recent_questions": [
            {
                "id": log.id,
                "question": log.question,
                "confidence": log.confidence,
                "created_at": log.created_at.isoformat(),
            }
            for log in activity["recent_questions"]
        ],
        "recent_ai_task_runs": [
            {
                "id": run.id,
                "task_type_display": run.get_task_type_display(),
                "status_display": run.get_status_display(),
                "created_at": run.created_at.isoformat(),
            }
            for run in activity["recent_ai_task_runs"]
        ],
        "activity_feed": [
            {"icon": e["icon"], "text": e["text"], "at": e["at"].isoformat()}
            for e in events[:5]
        ],
        "permissions": user_permissions,
        "can_view_admin_area": can_view_admin_area,
    })


@api_view(["GET"])
@permission_classes([HasAdminAreaAccess])
def admin_overview_view(request):
    """
    Admin Overview (/admin/) as JSON - KPI cards with trend
    sparklines, the Documents Over Time / Document Types / Topics by
    Category charts, System Status, and the Recent Documents table.
    Gated the same coarse way as its template predecessor
    (HasAdminAreaAccess, see RAG.decorators.admin_area_required) - not
    behind any individual permission - since every role that gets the
    admin sidebar shell must always have an Overview to land on.
    """

    user = request.user

    try:
        chart_range = int(request.query_params.get("range", 7))
    except (TypeError, ValueError):
        chart_range = 7
    if chart_range not in DASHBOARD_CHART_RANGES:
        chart_range = 7

    stats = get_dashboard_stats(user)
    activity = get_recent_activity(user)
    knowledge_overview = get_knowledge_overview(user)
    document_types = get_document_type_breakdown(user)
    documents_over_time = get_documents_over_time(user, days=chart_range)
    recent_documents_table = get_recent_documents_table(user)
    role, can_view_admin_area, user_permissions = get_user_access_snapshot(user)

    events = [
        {"icon": "file-up", "text": f'"{doc.title}" uploaded', "at": doc.uploaded_at}
        for doc in activity["recent_documents"]
    ] + [
        {"icon": "message-square", "text": f'Asked: "{log.question[:60]}"', "at": log.created_at}
        for log in activity["recent_questions"]
    ]
    events.sort(key=lambda e: e["at"], reverse=True)

    return Response({
        "stats": {
            "total_documents": stats["total_documents"],
            "total_chunks": stats["total_chunks"],
            "today_queries": stats["today_queries"],
            "storage_used": stats["storage_used"],
            "ai_task_runs": stats["ai_task_runs"],
        },
        "kpi_trends": get_kpi_trends(user),
        "documents_over_time": documents_over_time,
        "documents_over_time_range": chart_range,
        "documents_over_time_ranges": list(DASHBOARD_CHART_RANGES),
        "document_types": document_types,
        "recent_documents_table": [
            {
                "id": row["id"],
                "title": row["title"],
                "owner": row["owner"],
                "file_type": row["file_type"],
                "chunk_count": row["chunk_count"],
                "size": row["size"],
                "size_bytes": row["size_bytes"],
                "uploaded_at": row["uploaded_at"].isoformat(),
                "status": row["status"],
            }
            for row in recent_documents_table
        ],
        "knowledge_overview": {
            "total_entities": knowledge_overview.get("total_entities", 0),
            "total_relationships": knowledge_overview.get("total_relationships", 0),
            "total_sources": knowledge_overview.get("total_sources", 0),
            "category_breakdown": knowledge_overview.get("category_breakdown", []),
        },
        "recent_documents": [
            {
                "id": doc.id,
                "title": doc.title,
                "uploaded_at": doc.uploaded_at.isoformat(),
                "file_size": doc.file_size,
            }
            for doc in activity["recent_documents"]
        ],
        "recent_ai_task_runs": [
            {
                "id": run.id,
                "task_type_display": run.get_task_type_display(),
                "status": run.status,
                "status_display": run.get_status_display(),
                "document_count": run.document_count,
                "created_at": run.created_at.isoformat(),
            }
            for run in activity["recent_ai_task_runs"]
        ],
        "activity_feed": [
            {"icon": e["icon"], "text": e["text"], "at": e["at"].isoformat()}
            for e in events[:5]
        ],
        "system_status": get_system_status(),
        "permissions": user_permissions,
        "can_view_admin_area": can_view_admin_area,
    })
