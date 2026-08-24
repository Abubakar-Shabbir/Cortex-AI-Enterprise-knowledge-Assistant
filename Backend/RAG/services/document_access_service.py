"""
Document Access Control - single source of truth for "can this user see
this document."

The rest of the app treats a document as accessible if the requesting
user owns it, it's in the Admin-managed Organization Library, or it's
been explicitly shared with them (directly, or via a Role they hold).
Every retrieval function (vector/BM25/graph search) and every
Document-Center view that isn't strictly owner-only (preview, download,
favorites, the Select Documents dialog) goes through
get_accessible_document_ids() rather than re-deriving this set itself,
so the access boundary only has one place to get right.

Fails closed: a missing/unauthenticated user always yields an empty
set, never "everyone" - mirrors the fail-closed contract
retrieval_service.py/bm25_service.py/graph_retrieval_service.py already
use for `user=None`.
"""

from django.db.models import Q

from ..models import Document
from .permission_service import get_user_role


def get_accessible_document_ids(user):
    """
    Every Document id `user` may view: owned ∪ Organization Library ∪
    shared directly with them ∪ shared with a Role they currently hold.
    Returns a set, computed fresh on every call (no caching) so a
    revoked share or role change takes effect on the very next query.
    """

    if user is None or not getattr(user, "is_authenticated", False):
        return set()

    scope = Q(user=user) | Q(is_org_library=True) | Q(shares__shared_with_user=user)

    role = get_user_role(user)
    if role is not None:
        scope |= Q(shares__shared_with_role=role)

    return set(Document.objects.filter(scope).values_list("id", flat=True))


def get_accessible_documents(user):
    """The queryset counterpart of get_accessible_document_ids(), for views that need Document objects rather than bare ids."""

    ids = get_accessible_document_ids(user)
    return Document.objects.filter(id__in=ids) if ids else Document.objects.none()


def can_view_document(user, document):
    return document is not None and document.id in get_accessible_document_ids(user)


def can_edit_document(user, document):
    """
    Owner-only, always - sharing and Organization Library membership
    grant view/download, never delete, re-versioning, or share
    management. There is no permission that widens this.
    """

    return user is not None and document is not None and document.user_id == user.id
