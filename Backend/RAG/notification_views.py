"""
Notification Center views - kept in their own module rather than added
to the already-3400-line RAG/views.py, the same "give a big new surface
its own file" pattern this project already uses elsewhere.

Every user has their own notification inbox regardless of role (like
Profile - never permission-gated as a whole page); only the admin
announcement broadcast is RBAC-gated.
"""

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import redirect, render

from .decorators import permission_required
from .services import notification_service
from .services.activity_log_service import log_activity

logger = logging.getLogger(__name__)

# Icon per notification_type - same "unlisted falls back to a generic
# icon" contract as RAG.views._ACTIVITY_ICONS, so a new event type
# added later (see CLAUDE.md's Notification Events section) never needs
# a template change to render sensibly.
_NOTIFICATION_ICONS = {
    "document.shared": "share-2",
    "document.access_revoked": "shield-off",
    "document.uploaded": "file-up",
    "document.processing_completed": "check-circle",
    "document.processing_failed": "x-circle",
    "ai_task.completed": "sparkles",
    "ai_task.failed": "alert-triangle",
    "account.verified": "badge-check",
    "account.password_changed": "key-round",
    "account.role_changed": "shield",
    "security.new_login": "shield-alert",
    "security.account_suspended": "user-x",
    "security.account_reactivated": "user-check",
    "system.announcement": "megaphone",
}
_DEFAULT_NOTIFICATION_ICON = "bell"


def _serialize(notification):
    return {
        "id": notification.id,
        "type": notification.notification_type,
        "category": notification.category,
        "icon": _NOTIFICATION_ICONS.get(notification.notification_type, _DEFAULT_NOTIFICATION_ICON),
        "title": notification.title,
        "message": notification.message,
        "action_url": notification.action_url,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat(),
        "created_at_display": notification.created_at.strftime("%b %d, %Y %H:%M"),
    }


@login_required
def notification_center_view(request):
    """Full paginated notification history - own account only, filterable by category."""

    category = request.GET.get("category") or None

    notifications = notification_service.list_notifications(request.user, category=category)

    paginator = Paginator(notifications, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    # Icon annotated onto each row here (dict lookups by a template
    # variable aren't directly expressible in Django template syntax)
    # rather than in the template - same "enrich the object as it flows
    # through" pattern reranker_service.py uses for rerank_score.
    for notification in page_obj:
        notification.icon = _NOTIFICATION_ICONS.get(notification.notification_type, _DEFAULT_NOTIFICATION_ICON)

    categories = sorted({n.category for n in notification_service.list_notifications(request.user)})

    return render(
        request,
        "notifications/center.html",
        {
            "page_obj": page_obj,
            "categories": categories,
            "active_category": category,
        },
    )


@login_required
def notification_unread_count(request):
    """The poll target - JSON only, cheap uncached count. Called every ~25s by the topbar bell."""

    return JsonResponse({"count": notification_service.get_unread_count(request.user)})


@login_required
def notification_list_json(request):
    """Lightweight JSON list for the topbar dropdown - lazy-fetched on first open, not on every page load."""

    try:
        limit = min(int(request.GET.get("limit", 10)), 50)
    except (TypeError, ValueError):
        limit = 10

    notifications = notification_service.list_notifications(request.user, limit=limit)

    return JsonResponse({"notifications": [_serialize(n) for n in notifications]})


@login_required
def notification_mark_read(request, notification_id):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    marked = notification_service.mark_read(notification_id, request.user)

    return JsonResponse({"marked": marked})


@login_required
def notification_mark_all_read(request):
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    count = notification_service.mark_all_read(request.user)

    return JsonResponse({"marked": count})


@permission_required("notifications.send_announcement")
def admin_send_announcement_view(request):
    """Fan out a system.announcement notification to every active user - in-app + email (system announcements are user-toggleable, unlike account/security)."""

    if request.method == "POST":
        title = request.POST.get("title", "").strip()
        body = request.POST.get("message", "").strip()

        if not title or not body:
            messages.error(request, "Both a title and a message are required.")
        else:
            recipients = User.objects.filter(is_active=True)
            sent = 0
            for recipient in recipients:
                notification_service.create_notification(
                    recipient=recipient,
                    actor=request.user,
                    notification_type="system.announcement",
                    title=title,
                    message=body,
                )
                sent += 1

            log_activity(
                actor=request.user,
                action="notification.announcement_sent",
                description=f'{request.user.username} sent an announcement to {sent} user(s): "{title}"',
                request=request,
            )
            messages.success(request, f"Announcement sent to {sent} user(s).")

        return redirect("admin_send_announcement")

    return render(request, "notifications/admin_announce.html", {})
