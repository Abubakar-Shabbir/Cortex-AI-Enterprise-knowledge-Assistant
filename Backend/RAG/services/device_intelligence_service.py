"""
Device Intelligence Service

Real device/browser/OS parsing and session/presence data for the
Profile module - login history, active sessions, and online status.
Every function here reads from data that's actually captured elsewhere
(ActivityLog's ip/user_agent columns, Django's own session store) -
nothing is fabricated or hardcoded, per the Profile module's "no mock
data" requirement.

Follows the same never-raise contract as geolocation_service.py: a
parsing/lookup failure degrades to "Unknown"/empty results, it never
breaks the page rendering it.
"""

import logging

from django.contrib.sessions.models import Session
from django.utils import timezone
from user_agents import parse as parse_user_agent

from ..models import ActivityLog

logger = logging.getLogger(__name__)

UNKNOWN_DEVICE = {"device_type": "Unknown", "browser": "Unknown", "os": "Unknown"}

ONLINE_THRESHOLD_MINUTES = 5


def parse_device(user_agent_string):
    """
    Resolve a raw User-Agent header into {"device_type", "browser", "os"}
    via the `user_agents` library (real parsing, not regex guesswork).
    Never raises - a blank string or an unparseable value falls back to
    UNKNOWN_DEVICE.
    """

    if not user_agent_string:
        return dict(UNKNOWN_DEVICE)

    try:
        ua = parse_user_agent(user_agent_string)

        if ua.is_tablet:
            device_type = "Tablet"
        elif ua.is_mobile:
            device_type = "Mobile"
        elif ua.is_pc:
            device_type = "Desktop"
        else:
            device_type = "Other"

        browser = ua.browser.family or "Unknown"
        if ua.browser.version_string:
            browser = f"{browser} {ua.browser.version_string}"

        os_name = ua.os.family or "Unknown"
        if ua.os.version_string:
            os_name = f"{os_name} {ua.os.version_string}"

        return {"device_type": device_type, "browser": browser, "os": os_name}
    except Exception:
        logger.exception("Failed to parse User-Agent string.")
        return dict(UNKNOWN_DEVICE)


def get_login_history(user, limit=10):
    """
    The user's most recent user.login events, each enriched with parsed
    device/browser/OS and the IP/location already captured on that row.
    Real rows only - an account with no logins yet (pre-dates this
    tracking, or was created directly) just gets an empty list.
    """

    logs = (
        ActivityLog.objects.filter(actor=user, action="user.login")
        .order_by("-created_at")[:limit]
    )

    history = []
    for log in logs:
        device = parse_device(log.user_agent)
        location_parts = [p for p in (log.city, log.region, log.country) if p]
        history.append({
            "at": log.created_at,
            "ip_address": log.ip_address,
            "location": ", ".join(location_parts) if location_parts else "",
            "device_type": device["device_type"],
            "browser": device["browser"],
            "os": device["os"],
        })

    return history


def get_active_sessions(user, current_session_key=None):
    """
    Every non-expired Django session belonging to this user, decoded
    from the real django_session table (the project uses Django's
    default DB-backed session engine - no SESSION_ENGINE override in
    settings.py). Cross-referenced against the request's own
    session_key so the template can label "this device" accurately.
    """

    sessions = []
    user_id_str = str(user.id)

    for session in Session.objects.filter(expire_date__gt=timezone.now()):
        try:
            data = session.get_decoded()
        except Exception:
            continue

        if data.get("_auth_user_id") != user_id_str:
            continue

        sessions.append({
            "session_key": session.session_key,
            "is_current": session.session_key == current_session_key,
            "expire_date": session.expire_date,
        })

    sessions.sort(key=lambda s: s["is_current"], reverse=True)
    return sessions


def get_last_active(user):
    """
    The most recent activity timestamp for this user, from ANY
    ActivityLog row - including the generic "page.*" rows
    RAG.middleware.RequestActivityMiddleware writes for every click, so
    this reflects real, current usage rather than only login events.
    Falls back to user.last_login for an account with no ActivityLog
    rows at all (e.g. it logged in before this tracking existed).
    """

    latest = (
        ActivityLog.objects.filter(actor=user)
        .order_by("-created_at")
        .values_list("created_at", flat=True)
        .first()
    )

    return latest or user.last_login


def is_online(user, threshold_minutes=ONLINE_THRESHOLD_MINUTES):
    """
    True only if the user has both a live session AND activity within
    the last `threshold_minutes` - a disclosed, real threshold rather
    than a stored/fabricated flag.
    """

    last_active = get_last_active(user)
    if not last_active:
        return False

    recent_enough = (timezone.now() - last_active).total_seconds() <= threshold_minutes * 60
    if not recent_enough:
        return False

    return len(get_active_sessions(user)) > 0


INACTIVE_THRESHOLD_DAYS = 90


def get_account_health(user):
    """
    A computed, not stored, health label from real signals - is_active
    (existing suspend/reactivate flow) and recency of get_last_active().
    Recomputed on every read, same "no state machine, just recompute
    from current signals" approach ErrorGroup.severity already uses.
    """

    if not user.is_active:
        return {"label": "Suspended", "category": "danger"}

    last_active = get_last_active(user)
    if not last_active:
        return {"label": "Never active", "category": "neutral"}

    days_inactive = (timezone.now() - last_active).days
    if days_inactive >= INACTIVE_THRESHOLD_DAYS:
        return {"label": f"Inactive {days_inactive}+ days", "category": "warning"}

    return {"label": "Good standing", "category": "success"}
