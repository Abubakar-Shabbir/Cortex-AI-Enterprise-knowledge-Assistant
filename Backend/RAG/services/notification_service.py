"""
Notification Service

The one generic entry point every feature (document sharing today;
document processing, AI Tasks, account/security events, system
announcements later - see CLAUDE.md's Notification Events section)
calls to notify a user, in-app and optionally by email. Distinct from
RAG.services.activity_log_service.log_activity() - that's a system-wide
audit trail keyed on the *actor*; this is a per-user inbox keyed on the
*recipient*. Never conflate the two, never populate one from the other.

Every function here follows the same never-raise contract as the rest
of RAG/services/*.py: a failure here must never break the primary
action (sharing a document, finishing an AI Task, ...) that triggered
it. Email delivery in particular is always dispatched via
RAG.services.task_runner.submit() so a slow/failing SMTP server can
never block or fail the caller's request.
"""

import logging

from django.urls import reverse
from django.utils import timezone

from ..models import Notification, NotificationPreference

logger = logging.getLogger(__name__)

# Category namespaces (Notification.category - the first segment of
# notification_type) that always email regardless of NotificationPreference
# - security-relevant and account-lifecycle events are never
# user-silenceable, the same "some things aren't optional" stance
# RAG/decorators.py's RBAC checks already take for the Admin role.
ALWAYS_EMAIL_CATEGORIES = frozenset({"account", "security"})


def get_or_create_preferences(user) -> NotificationPreference:
    preferences, _ = NotificationPreference.objects.get_or_create(user=user)
    return preferences


def should_email(recipient, notification_type: str) -> bool:
    """
    True if `recipient` should get an emailed copy of a `notification_type`
    event. Always True for ALWAYS_EMAIL_CATEGORIES; otherwise checks
    whether the category has been opted out of via NotificationPreference.
    Never raises - a lookup failure degrades to "send the email" (the
    safer default: a missed notification is worse than an unwanted one).
    """

    category = notification_type.split(".")[0]

    if category in ALWAYS_EMAIL_CATEGORIES:
        return True

    try:
        preferences = get_or_create_preferences(recipient)
        return category not in preferences.disabled_email_categories
    except Exception:
        logger.exception("should_email: failed to load preferences for %s, defaulting to send", recipient)
        return True


def create_notification(
    recipient,
    notification_type: str,
    title: str,
    message: str,
    *,
    actor=None,
    data=None,
    action_url: str = "",
    send_email: bool = True,
) -> "Notification | None":
    """
    Creates one Notification row and, if warranted, backgrounds an
    emailed copy. Never raises to the caller - any failure (bad
    recipient, DB error) is logged and returns None rather than
    propagating into the caller's primary action.
    """

    if recipient is None or not getattr(recipient, "is_authenticated", True):
        logger.warning("create_notification: no valid recipient for type=%s", notification_type)
        return None

    try:
        notification = Notification.objects.create(
            recipient=recipient,
            actor=actor,
            notification_type=notification_type,
            title=title,
            message=message,
            data=data or {},
            action_url=action_url,
        )
    except Exception:
        logger.exception("create_notification: failed to create notification type=%s recipient=%s", notification_type, recipient.id)
        return None

    if send_email and should_email(recipient, notification_type):
        from . import task_runner
        from ..tasks import send_notification_email_task
        task_runner.submit(send_notification_email_task, notification.id)

    return notification


def mark_read(notification_id, user) -> bool:
    """Ownership-checked - a user can only ever mark their own notifications read. Returns False (not an error) if the id doesn't belong to `user` or doesn't exist."""

    updated = Notification.objects.filter(id=notification_id, recipient=user, is_read=False).update(
        is_read=True, read_at=timezone.now(),
    )
    return updated > 0


def mark_all_read(user) -> int:
    return Notification.objects.filter(recipient=user, is_read=False).update(is_read=True, read_at=timezone.now())


def get_unread_count(user) -> int:
    """
    Deliberately uncached (unlike context_processors.sidebar_status()'s
    30s-cached system_status) - this is read on every poll and must
    reflect mark_read()/mark_all_read() on the very next request. The
    underlying query is a single indexed count, cheap enough at this
    project's scale to run uncached.
    """

    if user is None or not getattr(user, "is_authenticated", False):
        return 0

    return Notification.objects.filter(recipient=user, is_read=False).count()


def list_notifications(user, *, unread_only: bool = False, category: str = None, limit: int = None):
    queryset = Notification.objects.filter(recipient=user)

    if unread_only:
        queryset = queryset.filter(is_read=False)

    if category:
        queryset = queryset.filter(notification_type__startswith=f"{category}.")

    if limit:
        queryset = queryset[:limit]

    return queryset


def document_open_url(document_id: int) -> str:
    """
    Shared helper so every "document.shared"-family notification's
    action_url points at the same place: document_download (no
    ?download=1, so it opens inline rather than forcing a file save) -
    the exact link documents/shared_with_me.html's own "Open" toolbar
    button already uses. Already access-checked server-side via
    document_access_service.get_accessible_document_ids() inside that
    view, so a notification link is never a way to bypass authorization
    - clicking it re-checks access at request time, same as visiting
    the page and clicking "Open" would.
    """

    return reverse("document_download", args=[document_id])
