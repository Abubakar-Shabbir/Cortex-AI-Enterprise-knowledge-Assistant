"""
Documents (My Documents) as JSON - reuses the exact same service calls
RAG.views.documents_view/document_delete/document_embed/document_status/
document_archive_toggle/document_favorite_toggle/document_preview/
document_download already make. Upload still only saves the file
(processing_status=PENDING); Embed is a separate explicit action, same
two-step flow the classic page uses. No document-processing/business
logic is duplicated here - every endpoint below is a thin JSON
adapter over the existing services module.
"""

import os

from django.conf import settings
from django.core.paginator import Paginator
from django.db.models import Count, F, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import Category, Collection, Document, DocumentAccessLog, Favorite, Role, Tag
from ..services.activity_log_service import log_activity
from ..services.categories_service import list_categories
from ..services.collections_service import add_document_to_collection, list_collections
from ..services.document_access_service import get_accessible_document_ids
from ..services.document_library_service import annotate_document_status, filter_and_sort_documents
from ..services.favorites_service import favorite_ids_for, toggle_favorite
from ..services.permission_service import user_has_permission
from ..services.preview_service import get_document_preview_text
from ..services.tags_service import list_tags
from ..services.upload_service import process_uploaded_document, upload_document
from ..utils.formatting import format_bytes
from .permissions import HasPagePermission


def _serialize_item(item, favorited_ids):
    doc = item["doc"]
    return {
        "id": doc.id,
        "title": doc.title,
        "file_type": doc.file_type,
        "uploaded_at": doc.uploaded_at.isoformat(),
        "chunk_count": doc.chunk_count,
        "status": item["status"],
        "percent": item["percent"],
        "file_size": item["file_size"],
        "is_favorite": doc.id in favorited_ids,
        "is_archived": doc.is_archived,
        "is_org_library": doc.is_org_library,
        "category_id": doc.category_id,
    }


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.documents")])
def documents_list_view(request):
    owned = Document.objects.filter(user=request.user)

    total_documents = owned.count()
    embedded_count = owned.annotate(embedded_chunks=Count("chunks__vector")).filter(
        chunk_count__gt=0, embedded_chunks__gte=F("chunk_count")
    ).count()
    total_storage = owned.aggregate(total=Sum("file_size"))["total"] or 0
    archived_count = owned.filter(is_archived=True).count()
    favorites_count = Favorite.objects.filter(user=request.user).count()

    documents = filter_and_sort_documents(
        owned.annotate(embedded_chunks=Count("chunks__vector")), request.query_params
    )

    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.query_params.get("page"))

    documents_data = annotate_document_status(page_obj.object_list)
    favorited_ids = favorite_ids_for(request.user, [item["doc"].id for item in documents_data])

    return Response({
        "results": [_serialize_item(item, favorited_ids) for item in documents_data],
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "count": paginator.count,
        "stats": {
            "total_documents": total_documents,
            "embedded_count": embedded_count,
            "total_storage": format_bytes(total_storage),
            "archived_count": archived_count,
            "favorites_count": favorites_count,
        },
    })


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.documents")])
def documents_meta_view(request):
    """Categories/tags/collections for the filter dropdowns + upload form - same lists documents_view passes to the template."""

    return Response({
        "categories": [{"id": c.id, "name": c.name} for c in list_categories(request.user)],
        "tags": [{"id": t.id, "name": t.name} for t in list_tags(request.user)],
        "collections": [{"id": c.id, "name": c.name} for c in list_collections(request.user)],
        "can_manage_org_library": user_has_permission(request.user, "documents.manage_org_library"),
        "can_share": user_has_permission(request.user, "documents.share"),
        "allowed_file_extensions": [ext.lstrip(".") for ext in settings.ALLOWED_FILE_EXTENSIONS],
    })


@api_view(["POST"])
@permission_classes([HasPagePermission("pages.documents")])
def document_upload_view(request):
    file = request.FILES.get("document")
    if not file:
        return Response({"error": "A file is required."}, status=400)

    title = os.path.splitext(file.name)[0][:200]

    try:
        document = upload_document(user=request.user, title=title, file=file)
    except ValueError as e:
        return Response({"error": str(e)}, status=400)

    collection_id = request.data.get("collection_id")
    if collection_id:
        collection = Collection.objects.filter(id=collection_id, user=request.user).first()
        if collection:
            add_document_to_collection(request.user, collection, document)

    if request.data.get("add_to_org_library") and user_has_permission(request.user, "documents.manage_org_library"):
        document.is_org_library = True
        document.save(update_fields=["is_org_library"])
        log_activity(
            actor=request.user,
            action="document.org_library_added",
            description=f'"{document.title}" added to the Organization Library by {request.user.username}',
            request=request,
        )

    return Response({"id": document.id, "title": document.title}, status=201)


@api_view(["DELETE"])
@permission_classes([HasPagePermission("pages.documents")])
def document_delete_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id, user=request.user)
    title = document.title

    document.file.delete(save=False)
    document.delete()

    log_activity(
        actor=request.user,
        action="document.deleted",
        description=f'"{title}" deleted by {request.user.username}',
        request=request,
    )

    return Response(status=204)


@api_view(["POST"])
@permission_classes([HasPagePermission("pages.documents")])
def document_embed_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id, user=request.user)

    if document.processing_status not in (Document.ProcessingStatus.PENDING, Document.ProcessingStatus.FAILED):
        return Response({"error": f'"{document.title}" has already been processed.'}, status=400)

    if settings.ENABLE_ASYNC_PROCESSING:
        from ..services import task_runner
        from ..tasks import process_document_task

        try:
            task_runner.submit(process_document_task, document.id)
        except Exception:
            try:
                process_uploaded_document(document)
            except Exception:
                return Response({"error": f'Processing "{document.title}" failed - check the server logs.'}, status=500)
    else:
        try:
            process_uploaded_document(document)
        except Exception:
            return Response({"error": f'Processing "{document.title}" failed - check the server logs.'}, status=500)

    return Response({"status": "started"})


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.documents")])
def document_status_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id, user=request.user)

    embedded_count = document.chunks.filter(vector__isnull=False).count()
    percent = round((embedded_count / document.chunk_count) * 100) if document.chunk_count else 0

    return Response({
        "status": document.processing_status,
        "chunk_count": document.chunk_count,
        "embedded_count": embedded_count,
        "percent": percent,
    })


@api_view(["POST"])
@permission_classes([HasPagePermission("pages.documents")])
def document_archive_toggle_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id, user=request.user)

    document.is_archived = not document.is_archived
    document.archived_at = timezone.now() if document.is_archived else None
    document.save(update_fields=["is_archived", "archived_at"])

    log_activity(
        actor=request.user,
        action="document.archived" if document.is_archived else "document.unarchived",
        description=f'"{document.title}" {"archived" if document.is_archived else "unarchived"} by {request.user.username}',
        request=request,
    )

    return Response({"id": document.id, "is_archived": document.is_archived})


@api_view(["POST"])
@permission_classes([HasPagePermission("pages.documents")])
def document_favorite_toggle_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id, id__in=get_accessible_document_ids(request.user))
    is_fav = toggle_favorite(request.user, document)
    return Response({"id": document.id, "is_favorite": is_fav})


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.documents")])
def document_preview_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id, id__in=get_accessible_document_ids(request.user))
    DocumentAccessLog.objects.create(user=request.user, document=document)
    return Response(get_document_preview_text(document))


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.documents")])
def document_download_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id, id__in=get_accessible_document_ids(request.user))

    if not document.file:
        raise Http404("File not found.")

    as_attachment = request.query_params.get("download") == "1"
    filename = os.path.basename(document.file.name)

    if as_attachment:
        log_activity(
            actor=request.user,
            action="document.downloaded",
            description=f'"{document.title}" downloaded by {request.user.username}',
            request=request,
        )

    return FileResponse(document.file.open("rb"), as_attachment=as_attachment, filename=filename)
