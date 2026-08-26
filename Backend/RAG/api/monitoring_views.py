"""
Monitoring endpoints for the React SPA - thin JSON wrappers around
RAG.views.monitoring_view's exact same service calls
(stats_service.get_system_status, health_service.get_health_status).
No new checks - same data, just serialized (ErrorGroup instances
become plain dicts).
"""

import django
from django.conf import settings
from rest_framework.decorators import api_view, permission_classes

from rest_framework.response import Response

from ..services.health_service import get_health_status
from ..services.permission_service import user_has_permission
from ..services.stats_service import get_system_status
from .permissions import HasPagePermission


def _serialize_errors(recent_errors):
    return {
        service: [
            {"message": g.message, "occurrence_count": g.occurrence_count, "last_seen": g.last_seen}
            for g in groups
        ]
        for service, groups in recent_errors.items()
    }


@api_view(["GET"])
@permission_classes([HasPagePermission("system.view_health")])
def monitoring_view(request):
    live_llm_check = request.query_params.get("live") == "1"

    status = get_system_status()
    health = get_health_status(live_llm_check=live_llm_check)

    uptime_seconds = health["uptime_seconds"]
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    uptime_display = (f"{days}d " if days else "") + f"{hours}h {minutes}m"

    return Response({
        "status": status,
        "health": {**health, "recent_errors": _serialize_errors(health["recent_errors"])},
        "chunk_size": settings.CHUNK_SIZE,
        "chunk_overlap": settings.CHUNK_OVERLAP,
        "top_k": settings.TOP_K,
        "django_version": django.get_version(),
        "uptime_display": uptime_display,
        "can_view_system_logs": user_has_permission(request.user, "system.view_ai_logs") or user_has_permission(request.user, "activity.view_all_logs"),
    })
