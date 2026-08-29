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
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, F, Sum
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import Category, Collection, Document, DocumentAccessLog, DocumentShare, DocumentVersion, Favorite, Role, Tag, UserRole
from ..services.activity_log_service import log_activity
from ..services.categories_service import list_categories
from ..services.collections_service import add_document_to_collection, list_collections
from ..services.document_access_service import get_accessible_document_ids, get_accessible_documents
from ..services.document_library_service import annotate_document_status, filter_and_sort_documents
from ..services.favorites_service import favorite_ids_for, list_favorites, toggle_favorite
from ..services import notification_service
from ..services.permission_service import user_has_permission
from ..services.preview_service import get_document_preview_text
from ..services.sharing_service import create_share, list_documents_shared_with, list_shares_for_document, revoke_share
from ..services.tags_service import list_tags
from ..services.upload_service import process_uploaded_document, upload_document, upload_new_version
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


def _serialize_item_with_owner(item, **extra):
    """Same shape _serialize_item uses, plus the owner username - for the cross-user listings (Favorites/Shared With Me/Org Library) whose tables show "Owner" as a column."""
    doc = item["doc"]
    return {
        "id": doc.id,
        "title": doc.title,
        "owner": doc.user.username,
        "file_type": doc.file_type,
        "uploaded_at": doc.uploaded_at.isoformat(),
        "status": item["status"],
        "file_size": item["file_size"],
        **extra,
    }


def _paginate_response(page_obj, paginator, results):
    return {
        "results": results,
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "count": paginator.count,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
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
        "can_view_knowledge_base": user_has_permission(request.user, "pages.knowledge_base"),
        "allowed_file_extensions": [ext.lstrip(".") for ext in settings.ALLOWED_FILE_EXTENSIONS],
        "assignable_roles": [{"id": r.id, "name": r.name} for r in Role.objects.order_by("name")],
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


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.documents")])
def select_documents_search_view(request):
    """JSON wrapper around RAG.views.select_documents_search - backs the shared SelectDocumentsDialog.jsx picker (AI Tasks, and anywhere else that needs to pick from the requester's accessible document set)."""

    documents = get_accessible_documents(request.user).select_related("user")

    q = request.query_params.get("q", "").strip()
    if q:
        documents = documents.filter(title__icontains=q)

    file_type = request.query_params.get("file_type", "").strip()
    if file_type:
        documents = documents.filter(file_type__iexact=file_type)

    documents = documents.order_by("title")

    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.query_params.get("page"))

    def owner_badge(doc):
        if doc.user_id == request.user.id:
            return "Mine"
        if doc.is_org_library:
            return "Org"
        return "Shared"

    return Response({
        "results": [
            {
                "id": doc.id,
                "title": doc.title,
                "file_type": doc.file_type,
                "uploaded_at": doc.uploaded_at.strftime("%Y-%m-%d"),
                "owner_badge": owner_badge(doc),
            }
            for doc in page_obj.object_list
        ],
        "has_next": page_obj.has_next(),
        "page": page_obj.number,
    })


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.documents")])
def favorites_view(request):
    documents = filter_and_sort_documents(
        list_favorites(request.user).annotate(embedded_chunks=Count("chunks__vector")), request.query_params,
    )
    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.query_params.get("page"))
    documents_data = annotate_document_status(page_obj.object_list)

    return Response(_paginate_response(
        page_obj, paginator,
        [_serialize_item_with_owner(item, is_favorite=True) for item in documents_data],
    ))


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.documents")])
def shared_with_me_view(request):
    """Read-only - row actions are limited to Open/Download, never Delete/Embed/Version, matching the classic page."""

    documents = filter_and_sort_documents(
        list_documents_shared_with(request.user).annotate(embedded_chunks=Count("chunks__vector")), request.query_params,
    )
    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.query_params.get("page"))
    documents_data = annotate_document_status(page_obj.object_list)

    return Response(_paginate_response(page_obj, paginator, [_serialize_item_with_owner(item) for item in documents_data]))


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.documents")])
def org_library_view(request):
    """Admin-managed Organization Library. Manage controls (toggle a document in/out) are gated behind "documents.manage_org_library", enforced for real in org_library_toggle_view below."""

    can_manage = user_has_permission(request.user, "documents.manage_org_library")

    org_documents = Document.objects.filter(is_org_library=True)
    total_org_documents = org_documents.count()
    total_org_storage = format_bytes(org_documents.aggregate(total=Sum("file_size"))["total"] or 0)

    documents = filter_and_sort_documents(
        org_documents.annotate(embedded_chunks=Count("chunks__vector")), request.query_params,
    )
    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.query_params.get("page"))
    documents_data = annotate_document_status(page_obj.object_list)

    add_query = request.query_params.get("add_q", "").strip()
    add_candidates = []
    if can_manage and add_query:
        add_candidates = [
            {"id": d.id, "title": d.title, "owner": d.user.username}
            for d in Document.objects.filter(is_org_library=False, title__icontains=add_query).select_related("user")[:20]
        ]

    return Response({
        **_paginate_response(page_obj, paginator, [_serialize_item_with_owner(item) for item in documents_data]),
        "total_org_documents": total_org_documents,
        "total_org_storage": total_org_storage,
        "can_manage": can_manage,
        "add_query": add_query,
        "add_candidates": add_candidates,
    })


@api_view(["POST"])
@permission_classes([HasPagePermission("documents.manage_org_library")])
def org_library_toggle_view(request, doc_id):
    """
    Add/remove ANY document (not just one the actor can already see)
    from the Organization Library - the "documents.manage_org_library"
    permission gate above is the entire access boundary here, same as
    the classic org_library_toggle view.
    """

    document = get_object_or_404(Document, id=doc_id)

    document.is_org_library = not document.is_org_library
    document.save(update_fields=["is_org_library"])

    log_activity(
        actor=request.user,
        action="document.org_library_added" if document.is_org_library else "document.org_library_removed",
        description=(
            f'"{document.title}" {"added to" if document.is_org_library else "removed from"} '
            f"the Organization Library by {request.user.username}"
        ),
        request=request,
    )

    return Response({"id": document.id, "is_org_library": document.is_org_library})


@api_view(["POST"])
@permission_classes([HasPagePermission("pages.documents")])
def documents_bulk_action_view(request):
    """JSON wrapper around RAG.views.documents_bulk_action - same owner-only vs. accessible-scoped action split, same silent-skip-outside-scope contract."""

    action = request.data.get("action")
    requested_ids = [int(i) for i in (request.data.get("document_ids") or []) if str(i).isdigit()]

    if not requested_ids:
        return Response({"error": "No documents selected."}, status=400)

    owner_only_actions = {"delete", "archive", "unarchive"}
    accessible_actions = {"favorite", "unfavorite", "add_to_collection"}

    collection = None
    if action == "add_to_collection":
        collection = get_object_or_404(Collection, id=request.data.get("collection_id"), user=request.user)

    if action in owner_only_actions:
        scoped = list(Document.objects.filter(id__in=requested_ids, user=request.user))
    elif action in accessible_actions:
        accessible_ids = get_accessible_document_ids(request.user)
        scoped = list(Document.objects.filter(id__in=set(requested_ids) & accessible_ids))
    else:
        return Response({"error": "Unknown action."}, status=400)

    succeeded = []

    for document in scoped:
        document_id = document.id
        if action == "delete":
            document.file.delete(save=False)
            document.delete()
        elif action == "archive":
            document.is_archived = True
            document.archived_at = timezone.now()
            document.save(update_fields=["is_archived", "archived_at"])
        elif action == "unarchive":
            document.is_archived = False
            document.archived_at = None
            document.save(update_fields=["is_archived", "archived_at"])
        elif action == "favorite":
            Favorite.objects.get_or_create(user=request.user, document=document)
        elif action == "unfavorite":
            Favorite.objects.filter(user=request.user, document=document).delete()
        elif action == "add_to_collection":
            add_document_to_collection(request.user, collection, document)
        succeeded.append(document_id)

    skipped = [i for i in requested_ids if i not in succeeded]

    if succeeded:
        log_activity(
            actor=request.user,
            action="document.bulk_action",
            description=f'{request.user.username} applied bulk action "{action}" to {len(succeeded)} document(s)',
            request=request,
        )

    return Response({"action": action, "succeeded": succeeded, "skipped": skipped})


def _share_target(s):
    if s.shared_with_user_id:
        return s.shared_with_user.username
    if s.shared_with_role_id:
        return f"Role: {s.shared_with_role.name}"
    return f"Pending invite: {s.invited_email}"


@api_view(["GET", "POST"])
@permission_classes([HasPagePermission("pages.documents")])
def document_share_view(request, doc_id):
    """JSON wrapper around RAG.views.document_share - GET lists current shares (owner-only), POST creates one."""

    document = get_object_or_404(Document, id=doc_id, user=request.user)

    if request.method == "POST":
        if not user_has_permission(request.user, "documents.share"):
            raise PermissionDenied("You don't have permission to share documents.")

        target_type = request.data.get("target_type")
        target_id = request.data.get("target_id")

        if target_type == "user" and not target_id:
            target_value = (request.data.get("target_username") or "").strip()

            if "@" in target_value:
                target_type = "email"
                target_id = target_value.lower()
            else:
                target_user = User.objects.filter(username=target_value).first()
                if target_user is None:
                    return Response({"error": "No user with that username."}, status=400)
                target_id = target_user.id

        try:
            share = create_share(document, request.user, target_type, target_id)
        except ValueError as e:
            return Response({"error": str(e)}, status=400)

        log_activity(
            actor=request.user,
            action="document.shared",
            description=f'"{document.title}" shared by {request.user.username}',
            request=request,
        )

        if share.shared_with_user_id:
            notification_service.create_notification(
                recipient=share.shared_with_user,
                actor=request.user,
                notification_type="document.shared",
                title=f"{request.user.username} shared a document with you",
                message=f'"{document.title}" was shared with you.',
                data={"document_id": document.id, "share_id": share.id},
                action_url=notification_service.document_open_url(document.id),
            )
        elif share.shared_with_role_id:
            role_holders = UserRole.objects.filter(role_id=share.shared_with_role_id).exclude(user_id=request.user.id).select_related("user")
            for user_role in role_holders:
                notification_service.create_notification(
                    recipient=user_role.user,
                    actor=request.user,
                    notification_type="document.shared",
                    title=f"{request.user.username} shared a document with your role",
                    message=f'"{document.title}" was shared with the {share.shared_with_role.name} role.',
                    data={"document_id": document.id, "share_id": share.id},
                    action_url=notification_service.document_open_url(document.id),
                )
        elif share.invited_email:
            from ..services import task_runner
            from ..tasks import send_share_invite_email_task
            task_runner.submit(send_share_invite_email_task, document.id, share.invited_email, request.user.username)

    shares = list_shares_for_document(document)

    return Response({"shares": [{"id": s.id, "target": _share_target(s), "created_at": s.created_at.strftime("%Y-%m-%d %H:%M")} for s in shares]})


@api_view(["POST"])
@permission_classes([HasPagePermission("pages.documents")])
def document_share_revoke_view(request, share_id):
    share = get_object_or_404(DocumentShare, id=share_id)

    document = share.document
    recipient = share.shared_with_user
    role = share.shared_with_role

    try:
        revoke_share(share, request.user)
    except ValueError as e:
        raise PermissionDenied(str(e))

    if recipient is not None:
        notification_service.create_notification(
            recipient=recipient,
            actor=request.user,
            notification_type="document.access_revoked",
            title="Document access revoked",
            message=f'Your access to "{document.title}" was revoked.',
            data={"document_id": document.id},
        )
    elif role is not None:
        role_holders = UserRole.objects.filter(role_id=role.id).exclude(user_id=request.user.id).select_related("user")
        for user_role in role_holders:
            notification_service.create_notification(
                recipient=user_role.user,
                actor=request.user,
                notification_type="document.access_revoked",
                title="Document access revoked",
                message=f'Access to "{document.title}" (shared with the {role.name} role) was revoked.',
                data={"document_id": document.id},
            )

    return Response({"revoked": True})


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.documents")])
def document_versions_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id, id__in=get_accessible_document_ids(request.user))

    versions = document.versions.all()

    return Response({
        "current_version": document.version_number,
        "versions": [
            {
                "id": v.id,
                "version_number": v.version_number,
                "file_type": v.file_type,
                "file_size": format_bytes(v.file_size),
                "replaced_at": v.replaced_at.strftime("%Y-%m-%d %H:%M"),
            }
            for v in versions
        ],
    })


@api_view(["POST"])
@permission_classes([HasPagePermission("pages.documents")])
def document_version_upload_view(request, doc_id):
    """Owner-only, like Embed - reuses the exact same sync-vs-background dispatch document_embed_view uses."""

    document = get_object_or_404(Document, id=doc_id, user=request.user)
    file = request.FILES.get("file")

    if not file:
        return Response({"error": "Choose a file to upload as the new version."}, status=400)

    try:
        upload_new_version(document, file)
    except ValueError as e:
        return Response({"error": str(e)}, status=400)

    if settings.ENABLE_ASYNC_PROCESSING:
        from ..services import task_runner
        from ..tasks import process_document_task

        try:
            task_runner.submit(process_document_task, document.id)
        except Exception:
            try:
                process_uploaded_document(document)
            except Exception:
                return Response({"error": f'Processing the new version of "{document.title}" failed - check the server logs.'}, status=500)
    else:
        try:
            process_uploaded_document(document)
        except Exception:
            return Response({"error": f'Processing the new version of "{document.title}" failed - check the server logs.'}, status=500)

    return Response({"id": document.id, "version_number": document.version_number}, status=201)


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.documents")])
def document_version_download_view(request, version_id):
    version = get_object_or_404(DocumentVersion, id=version_id, document_id__in=get_accessible_document_ids(request.user))

    if not version.file:
        raise Http404("File not found.")

    return FileResponse(version.file.open("rb"), as_attachment=True, filename=os.path.basename(version.file.name))
