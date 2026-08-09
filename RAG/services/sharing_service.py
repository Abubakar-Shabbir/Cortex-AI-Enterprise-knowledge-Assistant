"""
Document Sharing - per-document grants to a specific user or role, on
top of the coarser Organization Library toggle. Both are read by
document_access_service.get_accessible_document_ids(); this module
only owns creating/listing/revoking DocumentShare rows.
"""

from ..models import DocumentShare, Role
from django.contrib.auth.models import User


def create_share(document, actor, target_type, target_id):
    """
    `actor` must own `document` - sharing is an owner-only action, the
    same boundary document_access_service.can_edit_document enforces
    elsewhere. Raises ValueError on a self-share, a share with a
    target that doesn't exist, or a duplicate (the model's own
    unique_together would also catch a duplicate, but a ValueError
    here is a cleaner message for the view to surface).
    """

    if document.user_id != actor.id:
        raise ValueError("Only the document's owner can share it.")

    if target_type == "user":
        target_user = User.objects.filter(id=target_id).first()
        if target_user is None:
            raise ValueError("That user doesn't exist.")
        if target_user.id == actor.id:
            raise ValueError("You already own this document.")
        if DocumentShare.objects.filter(document=document, shared_with_user=target_user).exists():
            raise ValueError("Already shared with that user.")
        return DocumentShare.objects.create(document=document, shared_with_user=target_user, shared_by=actor)

    if target_type == "role":
        target_role = Role.objects.filter(id=target_id).first()
        if target_role is None:
            raise ValueError("That role doesn't exist.")
        if DocumentShare.objects.filter(document=document, shared_with_role=target_role).exists():
            raise ValueError("Already shared with that role.")
        return DocumentShare.objects.create(document=document, shared_with_role=target_role, shared_by=actor)

    raise ValueError("Invalid share target.")


def revoke_share(share, actor):
    """
    Ownership-only, not permission-gated - deliberately so a document
    owner who's since lost the "documents.share" permission can still
    revoke a share they created; revoking access is safety-positive,
    never a privilege escalation, so it should never be blocked by a
    permission that was only ever meant to gate *granting* access.
    """

    if share.document.user_id != actor.id:
        raise ValueError("Only the document's owner can revoke its shares.")

    share.delete()


def list_shares_for_document(document):
    return document.shares.select_related("shared_with_user", "shared_with_role").order_by("-created_at")


def list_documents_shared_with(user):
    from ..models import Document
    from .permission_service import get_user_role
    from django.db.models import Q

    role = get_user_role(user)
    scope = Q(shares__shared_with_user=user)
    if role is not None:
        scope |= Q(shares__shared_with_role=role)

    return Document.objects.filter(scope).distinct()
