"""
Notification endpoints for the React SPA - thin JSON wrappers around
RAG.notification_views / RAG.services.notification_service, the same
per-user inbox the classic topbar bell + Notification Center page use.
No new business logic - same service calls, same icon-per-type map.
"""

from django.core.paginator import Paginator
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ..notification_views import _serialize
from ..services import notification_service


@api_view(["GET"])
def notifications_view(request):
    """Full paginated notification history - backs the Notification Center page."""

    category = request.GET.get("category") or None
    notifications = notification_service.list_notifications(request.user, category=category)

    paginator = Paginator(notifications, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    categories = sorted({n.category for n in notification_service.list_notifications(request.user)})

    return Response({
        "results": [_serialize(n) for n in page_obj],
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "count": paginator.count,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
        "categories": categories,
        "active_category": category,
    })


@api_view(["GET"])
def notification_unread_count_view(request):
    """Polled every ~25s by the topbar bell."""
    return Response({"count": notification_service.get_unread_count(request.user)})


@api_view(["GET"])
def notification_list_json_view(request):
    """Lightweight list for the topbar dropdown - lazy-fetched on first open."""

    try:
        limit = min(int(request.GET.get("limit", 10)), 50)
    except (TypeError, ValueError):
        limit = 10

    notifications = notification_service.list_notifications(request.user, limit=limit)
    return Response({"notifications": [_serialize(n) for n in notifications]})


@api_view(["POST"])
def notification_mark_read_view(request, notification_id):
    marked = notification_service.mark_read(notification_id, request.user)
    return Response({"marked": marked})


@api_view(["POST"])
def notification_mark_all_read_view(request):
    count = notification_service.mark_all_read(request.user)
    return Response({"marked": count})
