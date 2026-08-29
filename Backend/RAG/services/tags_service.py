"""Tags - user-scoped labels (each user keeps their own vocabulary, even on a shared/org document - see Tag's model docstring)."""

from ..models import Tag
from .document_library_service import unique_slug


def list_tags(user):
    return Tag.objects.filter(user=user).order_by("name")


def create_tag(user, name):
    name = (name or "").strip()
    if not name:
        raise ValueError("Tag name is required.")

    existing = Tag.objects.filter(user=user, name__iexact=name).first()
    if existing:
        return existing

    return Tag.objects.create(user=user, name=name, slug=unique_slug(Tag, user, name))


def delete_tag(user, tag_id):
    Tag.objects.filter(user=user, id=tag_id).delete()


def tag_document(user, document, tag):
    if tag.user_id != user.id:
        raise ValueError("Cannot use another user's tag.")
    document.tags.add(tag)


def untag_document(user, document, tag):
    if tag.user_id != user.id:
        raise ValueError("Cannot use another user's tag.")
    document.tags.remove(tag)
