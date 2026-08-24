"""
User Overview (/dashboard/) as JSON - reuses exactly the same service
calls templates/user_dashboard.html's view (RAG.views.user_dashboard)
already makes. No aggregate query is reimplemented here.
"""

from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..services.knowledge_service import get_knowledge_overview
from ..services.permission_service import get_user_access_snapshot
from ..services.stats_service import get_dashboard_stats, get_recent_activity


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
