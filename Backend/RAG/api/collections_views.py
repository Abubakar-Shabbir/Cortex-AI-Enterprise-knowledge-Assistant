"""
Collections endpoints for the React SPA - thin JSON wrappers around
RAG.views.collections_view/collection_detail_view's exact same service
calls (collections_service.py). No new business logic.
"""

from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import Collection, Document
from ..services.collections_service import (
    add_document_to_collection,
    create_collection,
    delete_collection,
    list_collections,
    remove_document_from_collection,
    rename_collection,
)
from ..services.document_access_service import get_accessible_document_ids
from ..services.document_library_service import annotate_document_status, filter_and_sort_documents
from .documents_views import _serialize_item_with_owner, _paginate_response
from .permissions import HasPagePermission


def _serialize_collection(c):
    return {"id": c.id, "name": c.name, "description": c.description, "doc_count": c.doc_count}


@api_view(["GET", "POST"])
@permission_classes([HasPagePermission("pages.documents")])
def collections_view(request):
    if request.method == "POST":
        action = request.data.get("action")

        if action == "create":
            try:
                create_collection(request.user, request.data.get("name", ""), request.data.get("description", ""))
            except ValueError as e:
                return Response({"error": str(e)}, status=400)
        elif action == "rename":
            collection = get_object_or_404(Collection, id=request.data.get("collection_id"), user=request.user)
            try:
                rename_collection(request.user, collection, request.data.get("name", ""))
            except ValueError as e:
                return Response({"error": str(e)}, status=400)
        elif action == "delete":
            collection = get_object_or_404(Collection, id=request.data.get("collection_id"), user=request.user)
            delete_collection(request.user, collection)
        else:
            return Response({"error": "Unknown action."}, status=400)

    return Response({"collections": [_serialize_collection(c) for c in list_collections(request.user)]})


@api_view(["GET", "POST"])
@permission_classes([HasPagePermission("pages.documents")])
def collection_detail_view(request, collection_id):
    collection = get_object_or_404(Collection, id=collection_id, user=request.user)

    if request.method == "POST":
        action = request.data.get("action")
        doc_id = request.data.get("doc_id")
        document = get_object_or_404(Document, id=doc_id, id__in=get_accessible_document_ids(request.user)) if doc_id else None

        if action == "add_document" and document:
            try:
                add_document_to_collection(request.user, collection, document)
            except ValueError as e:
                return Response({"error": str(e)}, status=400)
        elif action == "remove_document" and document:
            remove_document_from_collection(request.user, collection, document)
        else:
            return Response({"error": "Unknown action."}, status=400)

    documents = filter_and_sort_documents(
        Document.objects.filter(collections=collection).annotate(embedded_chunks=Count("chunks__vector")),
        request.query_params,
    )
    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.query_params.get("page"))
    documents_data = annotate_document_status(page_obj.object_list)

    return Response({
        "collection": {"id": collection.id, "name": collection.name, "description": collection.description},
        **_paginate_response(page_obj, paginator, [_serialize_item_with_owner(item) for item in documents_data]),
    })
