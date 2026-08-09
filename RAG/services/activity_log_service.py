"""
Activity Log Service

Writes workspace-wide audit trail entries (RAG.models.ActivityLog).
Follows the same never-raise contract as graph_extraction_service and
the Sprint 6-8 retrieval services: a logging failure must never break
the real action it's describing (a document delete, a role change),
so log_activity() swallows and logs its own exceptions instead of
propagating them.
"""

import logging

from ..models import ActivityLog
from .geolocation_service import get_client_ip, lookup_ip_location

logger = logging.getLogger(__name__)


def log_activity(actor, action, description, request=None):
    """
    Record one audit trail entry.

    Parameters
    ----------
    actor : User or None
        Who performed the action. None is valid (e.g. a system-initiated
        event with no human actor).
    action : str
        Namespaced event codename, e.g. "document.deleted", "user.suspended".
    description : str
        Human-readable summary shown in the Activity Logs table.
    request : HttpRequest or None
        The request that triggered this event, if any - used to resolve
        and attach the client IP address and its coarse geolocation
        (city/region/country). Omit for system-initiated events with no
        request in scope; the row is written with those fields blank.
    """

    ip_address = None
    location = {}
    user_agent = ""

    if request is not None:
        try:
            ip_address = get_client_ip(request)
            if ip_address:
                location = lookup_ip_location(ip_address)
            user_agent = request.META.get("HTTP_USER_AGENT", "")
        except Exception:
            logger.exception("Failed to resolve IP/location for activity log action '%s'.", action)

    try:
        ActivityLog.objects.create(
            actor=actor,
            action=action,
            description=description,
            ip_address=ip_address,
            user_agent=user_agent,
            city=location.get("city", ""),
            region=location.get("region", ""),
            country=location.get("country", ""),
            country_code=location.get("country_code", ""),
            latitude=location.get("latitude"),
            longitude=location.get("longitude"),
        )
        # Lets RequestActivityMiddleware (RAG/middleware.py) know this
        # click already produced a specific, business-meaningful row
        # (e.g. "document.deleted") so it doesn't also write a generic
        # "page.*" row for the exact same request - one click, one row.
        if request is not None:
            request._activity_logged = True
    except Exception:
        logger.exception("Failed to write activity log entry for action '%s'.", action)
