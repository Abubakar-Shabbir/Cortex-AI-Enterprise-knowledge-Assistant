from django.core.cache import cache

from .models import Document, QueryLog
from .services.stats_service import get_system_status


def sidebar_status(request):
    """
    Makes live system status and a short recent
    activity feed available on every authenticated
    page (sidebar footer, topbar notifications)
    without every view fetching it separately.
    Status is cached briefly since it costs a DB
    round trip.
    """

    if not request.user.is_authenticated:
        return {}

    events = []

    for doc in Document.objects.filter(user=request.user).order_by("-uploaded_at")[:3]:
        events.append({
            "icon": "file-up",
            "text": f'"{doc.title}" uploaded',
            "at": doc.uploaded_at,
        })

    for log in QueryLog.objects.filter(user=request.user).order_by("-created_at")[:3]:
        events.append({
            "icon": "message-square",
            "text": f'Asked: "{log.question[:60]}"',
            "at": log.created_at,
        })

    events.sort(key=lambda e: e["at"], reverse=True)

    return {
        "system_status": cache.get_or_set(
            "rag_system_status",
            get_system_status,
            30,
        ),
        "activity_feed": events[:5],
    }
