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

logger = logging.getLogger(__name__)


def log_activity(actor, action, description):
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
    """

    try:
        ActivityLog.objects.create(actor=actor, action=action, description=description)
    except Exception:
        logger.exception("Failed to write activity log entry for action '%s'.", action)
