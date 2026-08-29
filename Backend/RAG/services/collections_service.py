"""
Collections - personal folders. The owner need not own every document
inside a collection, only be able to access it (checked here via
document_access_service.can_view_document, not a DB constraint) - so
filing an Organization Library document or one shared with you into
your own folder is a legitimate, supported use case.
"""

from django.db.models import Count

from ..models import Collection, CollectionDocument
from .document_access_service import can_view_document


def list_collections(user):
    return Collection.objects.filter(user=user).annotate(doc_count=Count("items")).order_by("name")


def create_collection(user, name, description=""):
    name = (name or "").strip()
    if not name:
        raise ValueError("Collection name is required.")

    if Collection.objects.filter(user=user, name__iexact=name).exists():
        raise ValueError("You already have a collection with that name.")

    return Collection.objects.create(user=user, name=name, description=(description or "").strip())


def rename_collection(user, collection, name):
    if collection.user_id != user.id:
        raise ValueError("Not your collection.")

    name = (name or "").strip()
    if not name:
        raise ValueError("Collection name is required.")

    collection.name = name
    collection.save(update_fields=["name"])


def delete_collection(user, collection):
    if collection.user_id != user.id:
        raise ValueError("Not your collection.")

    collection.delete()


def add_document_to_collection(user, collection, document):
    if collection.user_id != user.id:
        raise ValueError("Not your collection.")

    if not can_view_document(user, document):
        raise ValueError("You don't have access to this document.")

    CollectionDocument.objects.get_or_create(collection=collection, document=document)


def remove_document_from_collection(user, collection, document):
    if collection.user_id != user.id:
        raise ValueError("Not your collection.")

    CollectionDocument.objects.filter(collection=collection, document=document).delete()
