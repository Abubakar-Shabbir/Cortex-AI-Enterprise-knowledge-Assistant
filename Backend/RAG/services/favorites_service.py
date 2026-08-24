"""Favorites - any document the user can access can be favorited, not just an owned one."""

from ..models import Document, Favorite
from .document_access_service import get_accessible_document_ids


def toggle_favorite(user, document):
    """Returns the new is_favorite state (True if just favorited, False if just unfavorited)."""

    favorite, created = Favorite.objects.get_or_create(user=user, document=document)

    if not created:
        favorite.delete()
        return False

    return True


def list_favorites(user):
    """
    Documents `user` has favorited, filtered through their current
    accessible set - a revoked share or an Organization Library
    removal silently drops the document out of Favorites rather than
    leaving a dangling/404 entry.
    """

    accessible_ids = get_accessible_document_ids(user)
    favorited_ids = set(Favorite.objects.filter(user=user).values_list("document_id", flat=True))

    return Document.objects.filter(id__in=accessible_ids & favorited_ids)


def is_favorite(user, document):
    return Favorite.objects.filter(user=user, document=document).exists()


def favorite_ids_for(user, document_ids):
    """Bulk-check helper for list views - which of `document_ids` are favorited by `user`."""

    return set(
        Favorite.objects.filter(user=user, document_id__in=document_ids).values_list("document_id", flat=True)
    )
