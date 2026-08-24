import csv
import json
import logging
import os
from datetime import timedelta

import django

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, F, Q, Sum
from django.http import (
    FileResponse, Http404, HttpResponse, HttpResponseBadRequest, HttpResponseNotAllowed, JsonResponse,
    StreamingHttpResponse,
)
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.utils.text import slugify

from .decorators import admin_area_required, permission_required, settings_access_required, system_logs_access_required
from .models import (
    ADMIN_ROLE_SLUG, ActivityLog, AIRequestTrace, AITaskRun, AITaskRunDocument, Category, Collection,
    Document, DocumentAccessLog, DocumentChunk, DocumentShare, DocumentVersion, Entity, ErrorGroup, Favorite,
    Permission, QueryLog, Role, Tag, UserProfile, UserRole,
)
from .services.activity_log_service import log_activity
from .services import device_intelligence_service
from .services.profile_completion_service import get_completion
from .services.categories_service import create_category, delete_category, list_categories, set_document_category
from .services.collections_service import (
    add_document_to_collection,
    create_collection,
    delete_collection,
    list_collections,
    remove_document_from_collection,
    rename_collection,
)
from .services.citation_service import render_answer_html
from .services.document_access_service import get_accessible_document_ids, get_accessible_documents
from .services.document_library_service import annotate_document_status, filter_and_sort_documents
from .services import error_intelligence_service
from .services.favorites_service import favorite_ids_for, list_favorites, toggle_favorite
from .services.health_service import get_health_status
from .services import observability_service
from .services.preview_service import get_document_preview_text
from .services.sharing_service import (
    create_share,
    list_documents_shared_with,
    list_shares_for_document,
    revoke_share,
)
from .services.tags_service import create_tag, delete_tag, list_tags, tag_document, untag_document
from .services.knowledge_service import (
    ENTITY_TYPE_COLORS,
    _build_topic_dataset,
    get_citation_explorer,
    get_document_knowledge,
    get_entity_type_color,
    get_graph_data,
    get_graph_insights,
    get_knowledge_insights,
    get_knowledge_overview,
    get_related_topics_for_citations,
    get_relation_types,
    get_relationships,
    get_topic_detail,
    get_topic_node_detail,
    get_topic_pair_relationship_detail,
    resolve_topics_for_citations,
    search_topics,
)
from .services.prompt_templates import is_not_found_answer, is_service_unavailable_answer
from .services.perf import timed_stage
from .services.query_service import answer_question, answer_question_stream
from .services.queries_service import (
    annotate_status,
    filter_and_sort_queries,
    get_queries_analytics,
    get_search_methods,
)
from .services import notification_service
from .services.reports_service import (
    AI_TASK_RESULTS_HEADER,
    AI_TASK_RUNS_REPORT_HEADER,
    COMPARISON_REPORT_HEADER,
    DOCUMENTS_REPORT_HEADER,
    KNOWLEDGE_TOPICS_REPORT_HEADER,
    QUERIES_REPORT_HEADER_METADATA,
    QUERIES_REPORT_HEADER_WITH_CONTENT,
    USAGE_REPORT_HEADER,
    get_ai_task_result_rows,
    get_ai_task_runs_report_rows,
    get_comparison_report_rows,
    get_documents_report_rows,
    get_knowledge_topics_report_rows,
    get_queries_report_rows,
    get_usage_report_rows,
)
from .services.permission_service import (
    SENSITIVE_PERMISSIONS,
    can_actor_assign_role,
    can_actor_manage_target_user,
    compute_updated_role_permissions,
    get_assignable_roles,
    get_dashboard_url_for_user,
    get_permission_modules,
    get_user_permission_set,
    has_any_settings_permission,
    is_admin,
    is_last_admin,
    user_has_permission,
)
from .services.retrieval_filters import RetrievalFilters
from .services.trace import bind_trace_id
from .services.stats_service import (
    get_activity_summary,
    get_analytics_data,
    get_comparison_report_data,
    get_dashboard_stats,
    get_document_type_breakdown,
    get_documents_over_time,
    get_kpi_trends,
    get_recent_activity,
    get_recent_documents_table,
    get_system_status,
)
from .services.llm_client import get_llm
from .services.system_config_service import (
    SettingsValidationError,
    get_config,
    get_llm_provider_options,
    save_config,
)
from .services.upload_service import process_uploaded_document, upload_document, upload_new_version
from .utils.formatting import format_bytes

logger = logging.getLogger(__name__)


@login_required
def home_redirect(request):
    """
    '/' - sends every logged-in user to their Overview: Admin Overview
    for any role with admin-area access, User Overview for everyone
    else (see permission_service.get_dashboard_url_for_user - neither
    is permission-gated as a whole page, only which page and which
    widgets on it). Existing templates keep linking to {% url 'home' %}
    as a stable "take me to my dashboard" entry point regardless of
    role.
    """

    return redirect(get_dashboard_url_for_user(request.user))


@login_required
def user_dashboard(request):
    """
    User Overview (/dashboard/) - a deliberately simpler overview than
    Admin Overview: stat cards, recent documents, recent questions,
    and quick actions - see templates/user_dashboard.html. Extends the
    same base.html shell (single sidebar/topbar) as every other page;
    only its content is distinct from Admin Overview. Reachable by any
    authenticated account (same as Profile, never permission-gated as
    a whole page) - the template itself shows only the widgets the
    viewer's own permissions cover (pages.documents, pages.ask_ai,
    ...), so a role with very few permissions still lands somewhere
    real instead of being blocked outright.
    """

    stats = get_dashboard_stats(request.user)
    activity = get_recent_activity(request.user)

    return render(
        request,
        "user_dashboard.html",
        {
            "stats": stats,
            "knowledge_overview": get_knowledge_overview(request.user),
            **activity,
        },
    )


DASHBOARD_CHART_RANGES = (7, 14, 30)


@admin_area_required
def admin_dashboard_view(request):
    """
    Admin Overview (/admin/) - KPI cards with trend sparklines,
    documents-over-time and document-type charts, and a recent
    documents table. system_status / activity_feed are already
    supplied globally by context_processors.sidebar_status.

    Reachable by any role with admin-area access (see
    RAG.decorators.admin_area_required), not gated behind its own
    dedicated permission - the same population the admin sidebar shell
    is already shown to must always have an Overview to land on, even
    a role granted only e.g. "system.view_health". The template scopes
    down which widgets actually render based on the viewer's other
    permissions (pages.documents, pages.ask_ai, ...) rather than
    blocking the page outright for a narrower role.

    "Documents Over Time" is the one widget with a real, working
    control - a `?range=` query param picks how many days it covers
    (DASHBOARD_CHART_RANGES), degrading to the 7-day default on
    anything missing/invalid rather than raising, the same
    tolerant-input pattern RetrievalFilters.from_request() uses.
    """

    try:
        chart_range = int(request.GET.get("range", 7))
    except (TypeError, ValueError):
        chart_range = 7
    if chart_range not in DASHBOARD_CHART_RANGES:
        chart_range = 7

    stats = get_dashboard_stats(request.user)
    activity = get_recent_activity(request.user)
    knowledge_overview = get_knowledge_overview(request.user)
    trends = get_analytics_data(request.user, days=7, knowledge_overview=knowledge_overview)

    return render(
        request,
        "dashboard.html",
        {
            "stats": stats,
            "trends": trends,
            "kpi_trends": get_kpi_trends(request.user),
            "documents_over_time": get_documents_over_time(request.user, days=chart_range),
            "documents_over_time_range": chart_range,
            "documents_over_time_ranges": DASHBOARD_CHART_RANGES,
            "document_types": get_document_type_breakdown(request.user),
            "recent_documents_table": get_recent_documents_table(request.user),
            "knowledge_overview": knowledge_overview,
            **activity,
        },
    )


@permission_required("pages.ask_ai")
def ask_ai(request):
    """
    Dedicated Ask AI page: submit a question, show the answer, sources,
    confidence, response time and search method used.

    Two ways to end up with a `result` to display:
    - POST a fresh question - runs the full retrieval + LLM pipeline
      (answer_question(), which also writes the QueryLog row).
    - GET with ?log_id=<id> - instantly replays an already-answered
      question straight from that QueryLog row, no retrieval, no LLM
      call, no new log entry. Scoped to request.user via the filter
      below, so one account can never view another's history this way.
    """

    result = None
    selected_document_ids = request.POST.getlist("document_ids")
    selected_file_types = request.POST.getlist("file_types")
    selected_uploaded_after = request.POST.get("uploaded_after", "")
    selected_uploaded_before = request.POST.get("uploaded_before", "")
    selected_collection_id = request.POST.get("collection_id", "")
    selected_category_id = request.POST.get("category_id", "")
    selected_tag_id = request.POST.get("tag_id", "")
    selected_org_library_only = request.POST.get("org_library_only") == "1"

    if request.method == "POST" and "question" in request.POST:

        question = request.POST.get("question", "").strip()

        if question:

            filters = RetrievalFilters.from_request(
                document_ids=selected_document_ids,
                file_types=selected_file_types,
                uploaded_after=selected_uploaded_after or None,
                uploaded_before=selected_uploaded_before or None,
                collection_id=selected_collection_id or None,
                category_id=selected_category_id or None,
                tag_id=selected_tag_id or None,
                org_library_only=selected_org_library_only,
            )

            from django.db import connection, reset_queries

            reset_queries()

            with bind_trace_id() as trace_id, timed_stage(
                "request processing (ask_ai) TOTAL", question_chars=len(question), trace_id=trace_id
            ):
                result = answer_question(
                    question,
                    user=request.user,
                    filters=filters,
                )

            if settings.DEBUG:
                # connection.queries is only populated in DEBUG mode -
                # a Django-documented behavior, not a bug - so this
                # summary is dev-only, matching "display timing
                # metrics in development logs".
                total_query_time = sum(float(q["time"]) for q in connection.queries) * 1000
                logger.info(
                    "[PERF] %-28s %8.1fms %s",
                    "database queries", total_query_time, f"count={len(connection.queries)}",
                )

    elif request.method == "GET" and request.GET.get("log_id"):

        log = QueryLog.objects.filter(id=request.GET["log_id"], user=request.user).first()

        if log:
            sources = log.sources or []
            citations = [source for source in sources if source.get("citation_number")]
            structured = log.structured_data or {}
            # AIRequestTrace, not QueryLog, is the record of which
            # provider/model actually answered (QueryLog predates that
            # tracking) - looked up via the same FK save_trace()
            # attaches at answer time, so a past answer's "Answered by"
            # badge is exactly what generated it, not a guess.
            trace = AIRequestTrace.objects.filter(query_log=log).only("provider", "model", "providers_attempted").first()
            result = {
                "id": log.id,
                "question": log.question,
                "answer": log.answer,
                "sources": sources,
                "citations": citations,
                "response_time_ms": log.response_time_ms,
                "confidence": log.confidence,
                "search_method": log.search_method,
                "llm_provider": trace.provider if trace else "",
                "llm_model": trace.model if trace else "",
                "llm_fallback_used": bool(trace and len(trace.providers_attempted or []) > 1),
                "from_history": True,
                # Same shape answer_question() returns (see query_service.py) -
                # key_points/table come from the QueryLog row itself (written
                # at answer time), related_topics is recomputed here since
                # it's cheap (a knowledge-graph lookup, no LLM call) and
                # wasn't worth persisting a second time alongside `sources`.
                "key_points": structured.get("key_points", []),
                "table": structured.get("table"),
                "related_topics": get_related_topics_for_citations(request.user, citations),
            }

    if result is not None:
        result["answer_html"] = render_answer_html(result["answer"])
        result["is_service_unavailable"] = is_service_unavailable_answer(result["answer"])
        result["is_not_found"] = is_not_found_answer(result["answer"]) and not result["is_service_unavailable"]

    recent_questions = QueryLog.objects.filter(
        user=request.user
    ).order_by("-created_at")[:6]

    # Widened (Enterprise Document Center) from owned-only to the full
    # accessible set - owned + Organization Library + shared-with-them
    # - so Ask AI can answer from any document the requester can see,
    # not just ones they uploaded themselves. Safe because
    # retrieval_service/bm25_service/graph_retrieval_service now scope
    # by the same accessible set (see document_access_service).
    documents = get_accessible_documents(request.user).order_by("title")

    selected_documents_json = [
        {"id": doc.id, "title": doc.title}
        for doc in documents.filter(id__in=[i for i in selected_document_ids if i.isdigit()])
    ] if selected_document_ids else []

    user_collections = list_collections(request.user)
    user_categories = list_categories(request.user)
    user_tags = list_tags(request.user)

    def _name_for(queryset, raw_id):
        if not raw_id or not raw_id.isdigit():
            return ""
        match = next((item for item in queryset if item.id == int(raw_id)), None)
        return match.name if match else ""

    selected_collection_name = _name_for(user_collections, selected_collection_id)
    selected_category_name = _name_for(user_categories, selected_category_id)
    selected_tag_name = _name_for(user_tags, selected_tag_id)

    # A human-readable summary of exactly what scoped this answer -
    # rendered inside the result card so there's no ambiguity about
    # whether a selection actually took effect. Empty when nothing was
    # filtered (the common case), so it never clutters an unscoped
    # answer with a line that says nothing.
    applied_filter_labels = []
    if result is not None:
        if selected_documents_json:
            names = ", ".join(d["title"] for d in selected_documents_json[:3])
            if len(selected_documents_json) > 3:
                names += f" +{len(selected_documents_json) - 3} more"
            applied_filter_labels.append(f"Documents: {names}")
        if selected_collection_name:
            applied_filter_labels.append(f"Collection: {selected_collection_name}")
        if selected_category_name:
            applied_filter_labels.append(f"Category: {selected_category_name}")
        if selected_tag_name:
            applied_filter_labels.append(f"Tag: {selected_tag_name}")
        if selected_org_library_only:
            applied_filter_labels.append("Organization Library only")
        if selected_file_types:
            applied_filter_labels.append("Type: " + ", ".join(t.upper() for t in selected_file_types))
        if selected_uploaded_after:
            applied_filter_labels.append(f"After {selected_uploaded_after}")
        if selected_uploaded_before:
            applied_filter_labels.append(f"Before {selected_uploaded_before}")

    # Suggested Questions: the user's own most-mentioned entities,
    # turned into a ready-to-ask prompt - real, derived from their
    # knowledge graph, not LLM-generated.
    suggested_questions = [
        f"What can you tell me about {entity.display_name}?"
        for entity in Entity.objects.filter(user=request.user).order_by("-mention_count")[:4]
    ]

    return render(
        request,
        "ask_ai.html",
        {
            "result": result,
            "recent_questions": recent_questions,
            "documents": documents,
            "selected_document_ids": selected_document_ids,
            "selected_documents_json": selected_documents_json,
            "selected_file_types": selected_file_types,
            "selected_uploaded_after": selected_uploaded_after,
            "selected_uploaded_before": selected_uploaded_before,
            "selected_collection_id": selected_collection_id,
            "selected_category_id": selected_category_id,
            "selected_tag_id": selected_tag_id,
            "selected_org_library_only": selected_org_library_only,
            "selected_collection_name": selected_collection_name,
            "selected_category_name": selected_category_name,
            "selected_tag_name": selected_tag_name,
            "applied_filter_labels": applied_filter_labels,
            "collections": user_collections,
            "categories": user_categories,
            "tags": user_tags,
            "suggested_questions": suggested_questions,
            "allowed_file_extensions": [ext.lstrip(".") for ext in settings.ALLOWED_FILE_EXTENSIONS],
        },
    )


def _resolve_ask_ai_filter_labels(
    selected_document_ids, selected_file_types, selected_uploaded_after,
    selected_uploaded_before, selected_collection_id, selected_category_id,
    selected_tag_id, selected_org_library_only, user,
):
    """
    The "Filtered by: ..." label list shown on an Ask AI result card -
    used only by ask_ai_stream (below), which needs the exact same
    labels the classic ask_ai view computes inline in its own body
    (kept untouched there to avoid risking that already-working view)
    so a streamed answer's result card is indistinguishable from a
    classic-POST one for the same filter selection.
    """

    documents = get_accessible_documents(user)

    selected_documents_json = [
        {"id": doc.id, "title": doc.title}
        for doc in documents.filter(id__in=[i for i in selected_document_ids if i.isdigit()])
    ] if selected_document_ids else []

    def _name_for(queryset, raw_id):
        if not raw_id or not raw_id.isdigit():
            return ""
        match = next((item for item in queryset if item.id == int(raw_id)), None)
        return match.name if match else ""

    selected_collection_name = _name_for(list_collections(user), selected_collection_id)
    selected_category_name = _name_for(list_categories(user), selected_category_id)
    selected_tag_name = _name_for(list_tags(user), selected_tag_id)

    applied_filter_labels = []

    if selected_documents_json:
        names = ", ".join(d["title"] for d in selected_documents_json[:3])
        if len(selected_documents_json) > 3:
            names += f" +{len(selected_documents_json) - 3} more"
        applied_filter_labels.append(f"Documents: {names}")
    if selected_collection_name:
        applied_filter_labels.append(f"Collection: {selected_collection_name}")
    if selected_category_name:
        applied_filter_labels.append(f"Category: {selected_category_name}")
    if selected_tag_name:
        applied_filter_labels.append(f"Tag: {selected_tag_name}")
    if selected_org_library_only:
        applied_filter_labels.append("Organization Library only")
    if selected_file_types:
        applied_filter_labels.append("Type: " + ", ".join(t.upper() for t in selected_file_types))
    if selected_uploaded_after:
        applied_filter_labels.append(f"After {selected_uploaded_after}")
    if selected_uploaded_before:
        applied_filter_labels.append(f"Before {selected_uploaded_before}")

    return applied_filter_labels


@permission_required("pages.ask_ai")
def ask_ai_stream(request):
    """
    SSE counterpart to ask_ai(): same inputs (question + filters via
    RetrievalFilters.from_request(), same permission gate), but streams
    the LLM's answer token-by-token via answer_question_stream() instead
    of blocking until the full answer is ready. Retrieval/context
    assembly still run synchronously first (already ~300ms - not worth
    streaming).

    ask_ai.html's fetch/ReadableStream handler (streamAnswer()) renders
    each "token" event live, then on the final "done" event swaps in
    this view's own server-rendered partials/_ask_ai_result.html HTML -
    the exact same template ask_ai() itself renders, so the streamed
    end state is never a JS reimplementation that could drift from the
    classic-POST end state.

    Never raises past the try/except below: an unexpected failure
    yields one "error" event instead of a broken/hung stream or a raw
    500, and ask_ai.html's JS treats that the same as a network error -
    falls back to a normal form submit through ask_ai() itself.
    """

    if request.method != "POST" or not request.POST.get("question", "").strip():
        return HttpResponseBadRequest("A question is required.")

    question = request.POST.get("question", "").strip()

    document_ids = request.POST.getlist("document_ids")
    file_types = request.POST.getlist("file_types")
    uploaded_after = request.POST.get("uploaded_after", "")
    uploaded_before = request.POST.get("uploaded_before", "")
    collection_id = request.POST.get("collection_id", "")
    category_id = request.POST.get("category_id", "")
    tag_id = request.POST.get("tag_id", "")
    org_library_only = request.POST.get("org_library_only") == "1"

    filters = RetrievalFilters.from_request(
        document_ids=document_ids,
        file_types=file_types,
        uploaded_after=uploaded_after or None,
        uploaded_before=uploaded_before or None,
        collection_id=collection_id or None,
        category_id=category_id or None,
        tag_id=tag_id or None,
        org_library_only=org_library_only,
    )

    applied_filter_labels = _resolve_ask_ai_filter_labels(
        selected_document_ids=document_ids,
        selected_file_types=file_types,
        selected_uploaded_after=uploaded_after,
        selected_uploaded_before=uploaded_before,
        selected_collection_id=collection_id,
        selected_category_id=category_id,
        selected_tag_id=tag_id,
        selected_org_library_only=org_library_only,
        user=request.user,
    )

    def event_stream():
        # Bound inside the generator itself, not around the view's call
        # to StreamingHttpResponse(event_stream()) - the generator body
        # only actually runs when Django later iterates it, on whatever
        # context is current at that point, so binding out there
        # wouldn't reliably be in effect once execution reaches here.
        with bind_trace_id() as trace_id:
            try:
                for event in answer_question_stream(question, user=request.user, filters=filters):

                    if event["type"] == "token":
                        yield f"data: {json.dumps({'type': 'token', 'text': event['text']})}\n\n"

                    elif event["type"] == "done":
                        result = event["result"]
                        result["answer_html"] = render_answer_html(result["answer"])
                        result["is_service_unavailable"] = is_service_unavailable_answer(result["answer"])
                        result["is_not_found"] = is_not_found_answer(result["answer"]) and not result["is_service_unavailable"]

                        html = render_to_string(
                            "partials/_ask_ai_result.html",
                            {"result": result, "applied_filter_labels": applied_filter_labels},
                        )
                        yield f"data: {json.dumps({'type': 'done', 'html': html})}\n\n"

            except Exception:
                logger.exception("[INFRA] ask_ai_stream: streaming failed for question=%r trace_id=%s", question, trace_id)
                yield f"data: {json.dumps({'type': 'error', 'trace_id': trace_id})}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"

    return response


@permission_required("pages.documents")
def documents_view(request):
    """
    Upload documents and manage the document
    library (open / download / delete).

    Upload only saves the file (fast, no title field to fill in - the
    title is the filename, extension stripped); the Embed button on
    each row (document_embed, below) is what triggers extract/chunk/
    embed/graph-enrich, so a large file doesn't make this request
    slow.
    """

    upload_error = None

    if request.method == "POST" and "document" in request.FILES:

        file = request.FILES.get("document")
        title = os.path.splitext(file.name)[0][:200]

        try:

            document = upload_document(
                user=request.user,
                title=title,
                file=file,
            )

            # One-click org/collection filing at upload time, so the
            # user doesn't have to upload, then separately open the
            # row menu to file it - both are optional, silently
            # ignored if left blank/unchecked.
            collection_id = request.POST.get("collection_id")
            if collection_id:
                collection = Collection.objects.filter(id=collection_id, user=request.user).first()
                if collection:
                    add_document_to_collection(request.user, collection, document)

            if request.POST.get("add_to_org_library") and user_has_permission(request.user, "documents.manage_org_library"):
                document.is_org_library = True
                document.save(update_fields=["is_org_library"])
                log_activity(
                    actor=request.user,
                    action="document.org_library_added",
                    description=f'"{document.title}" added to the Organization Library by {request.user.username}',
                    request=request,
                )

            return redirect("documents")

        except ValueError as e:

            upload_error = str(e)

    owned = Document.objects.filter(user=request.user)

    # Stat cards always reflect the full "My Documents" set, not the
    # currently filtered/paginated table below.
    total_documents = owned.count()
    embedded_count = owned.annotate(embedded_chunks=Count("chunks__vector")).filter(
        chunk_count__gt=0, embedded_chunks__gte=F("chunk_count")
    ).count()
    total_storage = owned.aggregate(total=Sum("file_size"))["total"] or 0
    archived_count = owned.filter(is_archived=True).count()
    favorites_count = Favorite.objects.filter(user=request.user).count()

    documents = filter_and_sort_documents(
        owned.annotate(embedded_chunks=Count("chunks__vector")), request.GET
    )

    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    documents_data = annotate_document_status(page_obj.object_list)
    favorited_ids = favorite_ids_for(request.user, [item["doc"].id for item in documents_data])

    for item in documents_data:
        item["is_favorite"] = item["doc"].id in favorited_ids

    return render(
        request,
        "documents.html",
        {
            "documents_data": documents_data,
            "page_obj": page_obj,
            "upload_error": upload_error,
            "search_query": request.GET.get("q", "").strip(),
            "filters": request.GET,
            "categories": list_categories(request.user),
            "tags": list_tags(request.user),
            "collections": list_collections(request.user),
            "can_manage_org_library": user_has_permission(request.user, "documents.manage_org_library"),
            "can_share": user_has_permission(request.user, "documents.share"),
            "assignable_roles": Role.objects.order_by("name"),
            "total_documents": total_documents,
            "embedded_count": embedded_count,
            "total_storage": format_bytes(total_storage),
            "archived_count": archived_count,
            "favorites_count": favorites_count,
        },
    )


@permission_required("pages.documents")
def document_delete(request, doc_id):

    if request.method == "POST":

        document = get_object_or_404(
            Document, id=doc_id, user=request.user
        )

        title = document.title

        document.file.delete(save=False)
        document.delete()

        log_activity(
            actor=request.user,
            action="document.deleted",
            description=f'"{title}" deleted by {request.user.username}',
            request=request,
        )

        messages.success(request, "Document deleted.")

    return redirect("documents")


@permission_required("pages.documents")
def document_archive_toggle(request, doc_id):
    """Owner-only, like document_delete - archiving is a mutation, never granted by sharing/org-library membership."""

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

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

    return JsonResponse({"id": document.id, "is_archived": document.is_archived})


@permission_required("pages.documents")
def document_preview(request, doc_id):
    """
    Extracted-text preview (JSON) - accessible-scoped, not owner-only,
    since previewing (unlike deleting/archiving) is exactly what a
    sharee or org-library viewer needs to do. Logs a DocumentAccessLog
    row, the same signal document_download does, powering Recent
    Documents.
    """

    document = get_object_or_404(Document, id=doc_id, id__in=get_accessible_document_ids(request.user))

    DocumentAccessLog.objects.create(user=request.user, document=document)

    return JsonResponse(get_document_preview_text(document))


@permission_required("pages.documents")
def document_favorite_toggle(request, doc_id):
    """Accessible-scoped, not owner-only - any document you can see is one you can favorite."""

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    document = get_object_or_404(Document, id=doc_id, id__in=get_accessible_document_ids(request.user))

    is_fav = toggle_favorite(request.user, document)

    return JsonResponse({"id": document.id, "is_favorite": is_fav})


@permission_required("pages.documents")
def favorites_view(request):
    documents = filter_and_sort_documents(
        list_favorites(request.user).annotate(embedded_chunks=Count("chunks__vector")),
        request.GET,
    )

    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    documents_data = annotate_document_status(page_obj.object_list)

    for item in documents_data:
        item["is_favorite"] = True

    return render(
        request,
        "documents/favorites.html",
        {"documents_data": documents_data, "page_obj": page_obj, "filters": request.GET},
    )


@permission_required("pages.documents")
def documents_bulk_action(request):
    """
    Bulk delete/archive/unarchive/favorite/unfavorite/add_to_collection
    over a checked set of rows from My Documents. Owner-only actions
    re-filter by `user=request.user` so a document outside the actor's
    ownership silently lands in `skipped`, never mutated;
    favorite/unfavorite/add_to_collection use the wider accessible set
    since none of them mutate the document itself.
    """

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        body = json.loads(request.body)
    except (ValueError, TypeError):
        return JsonResponse({"error": "Invalid request body."}, status=400)

    action = body.get("action")
    requested_ids = [int(i) for i in body.get("document_ids", []) if str(i).isdigit()]

    if not requested_ids:
        return JsonResponse({"error": "No documents selected."}, status=400)

    owner_only_actions = {"delete", "archive", "unarchive"}
    accessible_actions = {"favorite", "unfavorite", "add_to_collection"}

    collection = None
    if action == "add_to_collection":
        collection = get_object_or_404(Collection, id=body.get("collection_id"), user=request.user)

    if action in owner_only_actions:
        scoped = list(Document.objects.filter(id__in=requested_ids, user=request.user))
    elif action in accessible_actions:
        accessible_ids = get_accessible_document_ids(request.user)
        scoped = list(Document.objects.filter(id__in=set(requested_ids) & accessible_ids))
    else:
        return JsonResponse({"error": "Unknown action."}, status=400)

    succeeded = []

    for document in scoped:
        document_id = document.id  # captured before delete(), which resets instance.pk to None
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

    return JsonResponse({"action": action, "succeeded": succeeded, "skipped": skipped})


@permission_required("pages.documents")
def tags_manage(request):
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create":
            try:
                create_tag(request.user, request.POST.get("name", ""))
            except ValueError as e:
                messages.error(request, str(e))
        elif action == "assign":
            document = get_object_or_404(Document, id=request.POST.get("doc_id"), id__in=get_accessible_document_ids(request.user))
            tag = get_object_or_404(Tag, id=request.POST.get("tag_id"), user=request.user)
            tag_document(request.user, document, tag)
        elif action == "unassign":
            document = get_object_or_404(Document, id=request.POST.get("doc_id"), id__in=get_accessible_document_ids(request.user))
            tag = get_object_or_404(Tag, id=request.POST.get("tag_id"), user=request.user)
            untag_document(request.user, document, tag)

        return redirect(request.POST.get("next") or "documents")

    return JsonResponse({"tags": [{"id": t.id, "name": t.name} for t in list_tags(request.user)]})


@permission_required("pages.documents")
def tag_delete(request, tag_id):
    if request.method == "POST":
        delete_tag(request.user, tag_id)
    return redirect(request.POST.get("next") or "documents")


@permission_required("pages.documents")
def categories_manage(request):
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create":
            try:
                create_category(request.user, request.POST.get("name", ""))
            except ValueError as e:
                messages.error(request, str(e))
        elif action == "set":
            document = get_object_or_404(Document, id=request.POST.get("doc_id"), id__in=get_accessible_document_ids(request.user))
            category_id = request.POST.get("category_id")
            category = get_object_or_404(Category, id=category_id, user=request.user) if category_id else None
            set_document_category(request.user, document, category)

        return redirect(request.POST.get("next") or "documents")

    return JsonResponse({"categories": [{"id": c.id, "name": c.name} for c in list_categories(request.user)]})


@permission_required("pages.documents")
def category_delete(request, category_id):
    if request.method == "POST":
        delete_category(request.user, category_id)
    return redirect(request.POST.get("next") or "documents")


@permission_required("pages.documents")
def collections_view(request):
    if request.method == "POST":
        action = request.POST.get("action")

        if action == "create":
            try:
                create_collection(request.user, request.POST.get("name", ""), request.POST.get("description", ""))
            except ValueError as e:
                messages.error(request, str(e))
        elif action == "rename":
            collection = get_object_or_404(Collection, id=request.POST.get("collection_id"), user=request.user)
            try:
                rename_collection(request.user, collection, request.POST.get("name", ""))
            except ValueError as e:
                messages.error(request, str(e))
        elif action == "delete":
            collection = get_object_or_404(Collection, id=request.POST.get("collection_id"), user=request.user)
            delete_collection(request.user, collection)

        return redirect("collections")

    return render(request, "documents/collections.html", {"collections": list_collections(request.user)})


@permission_required("pages.documents")
def collection_detail_view(request, collection_id):
    collection = get_object_or_404(Collection, id=collection_id, user=request.user)

    if request.method == "POST":
        action = request.POST.get("action")
        doc_id = request.POST.get("doc_id")
        document = get_object_or_404(Document, id=doc_id, id__in=get_accessible_document_ids(request.user)) if doc_id else None

        if action == "add_document" and document:
            try:
                add_document_to_collection(request.user, collection, document)
            except ValueError as e:
                messages.error(request, str(e))
        elif action == "remove_document" and document:
            remove_document_from_collection(request.user, collection, document)

        return redirect("collection_detail", collection_id=collection.id)

    documents = filter_and_sort_documents(
        Document.objects.filter(collections=collection).annotate(embedded_chunks=Count("chunks__vector")),
        request.GET,
    )

    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "documents/collection_detail.html",
        {
            "collection": collection,
            "documents_data": annotate_document_status(page_obj.object_list),
            "page_obj": page_obj,
            "breadcrumb_leaf": collection.name,
        },
    )


@permission_required("pages.documents")
def shared_with_me_view(request):
    """Read-only - row actions in the template are limited to Open/Download/Preview, never Delete/Embed/Version."""

    documents = filter_and_sort_documents(
        list_documents_shared_with(request.user).annotate(embedded_chunks=Count("chunks__vector")),
        request.GET,
    )

    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "documents/shared_with_me.html",
        {"documents_data": annotate_document_status(page_obj.object_list), "page_obj": page_obj, "filters": request.GET},
    )


@permission_required("pages.documents")
def org_library_view(request):
    """
    Admin-managed Organization Library. Manage controls (toggle a
    document in/out) are gated behind "documents.manage_org_library"
    both in the template and, as the real enforcement, in
    org_library_toggle below - this view itself is readable by anyone
    with "pages.documents" since Organization Library membership is
    what makes a document universally visible in the first place.
    """

    can_manage = user_has_permission(request.user, "documents.manage_org_library")

    org_documents = Document.objects.filter(is_org_library=True)
    total_org_documents = org_documents.count()
    total_org_storage = format_bytes(org_documents.aggregate(total=Sum("file_size"))["total"] or 0)

    documents = filter_and_sort_documents(
        org_documents.annotate(embedded_chunks=Count("chunks__vector")),
        request.GET,
    )

    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    add_query = request.GET.get("add_q", "").strip()
    add_candidates = []

    if can_manage and add_query:
        # Workspace-wide, metadata-only search (title/owner/type) so an
        # Admin can find and publish a document they don't personally
        # own or otherwise have access to yet - same "explicitly
        # authorized" cross-tenant read admin_query_detail_view uses,
        # never document content.
        add_candidates = list(
            Document.objects.filter(is_org_library=False, title__icontains=add_query)
            .select_related("user")
            .order_by("title")[:20]
        )

    return render(
        request,
        "documents/org_library.html",
        {
            "documents_data": annotate_document_status(page_obj.object_list),
            "page_obj": page_obj,
            "filters": request.GET,
            "can_manage": can_manage,
            "add_query": add_query,
            "add_candidates": add_candidates,
            "total_org_documents": total_org_documents,
            "total_org_storage": total_org_storage,
        },
    )


@permission_required("documents.manage_org_library")
def org_library_toggle(request, doc_id):
    """
    Add/remove ANY document (not just one the actor can already see)
    from the Organization Library - the whole point is for an Admin to
    publish someone else's document workspace-wide, e.g. Policies/
    SOPs/Manuals/Templates uploaded by various users, so this
    deliberately does NOT further restrict by
    get_accessible_document_ids - the "documents.manage_org_library"
    permission the decorator above already requires (Admin-only by
    default) is the entire access boundary here, mirroring
    admin_query_detail_view's "explicitly authorized auditing" -
    title/owner/type only ever cross a permission boundary this way,
    never document content.
    """

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

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

    return JsonResponse({"id": document.id, "is_org_library": document.is_org_library})


@permission_required("pages.documents")
def document_share(request, doc_id):
    """
    GET: list current shares (owner-only). POST: create a new share
    (owner + "documents.share" - the permission gates the *ability* to
    share at all; ownership is checked independently by
    sharing_service.create_share so the two boundaries can't be
    confused with each other).
    """

    document = get_object_or_404(Document, id=doc_id, user=request.user)

    if request.method == "POST":
        if not user_has_permission(request.user, "documents.share"):
            raise PermissionDenied("You don't have permission to share documents.")

        target_type = request.POST.get("target_type")
        target_id = request.POST.get("target_id")
        invite_email = None

        if target_type == "user" and not target_id:
            # The share dialog's "user" field accepts either a
            # username or an email address (documents.html's "Username
            # or email" input) - resolve it here so create_share()
            # only ever deals with a clean target, same as every other
            # target type. An email with no matching account becomes a
            # pending invite (target_type="email") rather than an
            # error - see sharing_service.create_share.
            target_value = request.POST.get("target_username", "").strip()

            if "@" in target_value:
                target_type = "email"
                invite_email = target_value.strip().lower()
                target_id = invite_email
            else:
                target_user = User.objects.filter(username=target_value).first()
                if target_user is None:
                    return JsonResponse({"error": "No user with that username."}, status=400)
                target_id = target_user.id

        try:
            share = create_share(document, request.user, target_type, target_id)
        except ValueError as e:
            return JsonResponse({"error": str(e)}, status=400)

        log_activity(
            actor=request.user,
            action="document.shared",
            description=f'"{document.title}" shared by {request.user.username}',
            request=request,
        )

        # Recipient notification - the one gap this feature had until
        # now (sharing only ever wrote the ActivityLog row above; the
        # recipient had no way to find out except visiting "Shared with
        # me" themselves). A role-target share fans out to every
        # current holder of that role - each gets their own
        # Notification row, same as an individual share would.
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
            # No User row exists yet for this address, so there's
            # nothing notification_service can attach a Notification
            # to (recipient is a required FK) - send the invite
            # directly. Backgrounded the same way every other email in
            # this feature is, so a slow/failing send can never fail
            # the share itself.
            from .services import task_runner
            from .tasks import send_share_invite_email_task
            task_runner.submit(send_share_invite_email_task, document.id, share.invited_email, request.user.username)

    shares = list_shares_for_document(document)

    def _share_target(s):
        if s.shared_with_user_id:
            return s.shared_with_user.username
        if s.shared_with_role_id:
            return f"Role: {s.shared_with_role.name}"
        return f"Pending invite: {s.invited_email}"

    return JsonResponse({
        "shares": [
            {
                "id": s.id,
                "target": _share_target(s),
                "created_at": s.created_at.strftime("%Y-%m-%d %H:%M"),
            }
            for s in shares
        ],
    })


@permission_required("pages.documents")
def document_share_revoke(request, share_id):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    share = get_object_or_404(DocumentShare, id=share_id)

    # Captured before revoke_share() deletes the row - simplest to read
    # correctly regardless of ORM post-delete instance-attribute
    # behavior, rather than relying on the (deleted) share object
    # afterward.
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

    return JsonResponse({"revoked": True})


@permission_required("pages.documents")
def document_versions(request, doc_id):
    """Read-only, accessible-scoped - anyone who can see the current version can see its history."""

    document = get_object_or_404(Document, id=doc_id, id__in=get_accessible_document_ids(request.user))

    versions = document.versions.all()

    return JsonResponse({
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


@permission_required("pages.documents")
def document_version_upload(request, doc_id):
    """
    Owner-only, like document_embed - uploading a new version is a
    mutation, never granted by sharing/org-library membership. Reuses
    document_embed's exact sync-vs-background-thread dispatch so a large
    re-processing pass behaves identically either way.
    """

    if request.method != "POST":
        return redirect("documents")

    document = get_object_or_404(Document, id=doc_id, user=request.user)
    file = request.FILES.get("file")

    if not file:
        messages.error(request, "Choose a file to upload as the new version.")
        return redirect("documents")

    try:
        upload_new_version(document, file)
    except ValueError as e:
        messages.error(request, str(e))
        return redirect("documents")

    if settings.ENABLE_ASYNC_PROCESSING:
        from .services import task_runner
        from .tasks import process_document_task

        try:
            task_runner.submit(process_document_task, document.id)
            messages.success(request, f'New version of "{document.title}" is processing in the background.')
        except Exception:
            # See document_embed's matching comment - graceful fallback
            # to the inline path already used when async processing is
            # off, rather than just surfacing an error.
            logger.exception("[INFRA] document_version_upload: background dispatch failed for document %s, falling back to inline processing", document.id)
            try:
                process_uploaded_document(document)
                messages.success(request, f'"{document.title}" updated to version {document.version_number} (background dispatch failed, so this ran immediately instead).')
            except Exception:
                messages.error(request, f'Processing the new version of "{document.title}" failed - check the server logs.')
    else:
        try:
            process_uploaded_document(document)
            messages.success(request, f'"{document.title}" updated to version {document.version_number}.')
        except Exception:
            messages.error(request, f'Processing the new version of "{document.title}" failed - check the server logs.')

    return redirect("documents")


@permission_required("pages.documents")
def document_version_download(request, version_id):
    version = get_object_or_404(
        DocumentVersion, id=version_id, document_id__in=get_accessible_document_ids(request.user)
    )

    if not version.file:
        raise Http404("File not found.")

    return FileResponse(version.file.open("rb"), as_attachment=True, filename=os.path.basename(version.file.name))


@permission_required("pages.documents")
def select_documents_search(request):
    """
    JSON search backing the reusable "Select Documents" dialog
    (templates/partials/_select_documents_dialog.html). Base queryset
    is the requester's full accessible set - owned + Organization
    Library + shared-with-them - never owner-only, since letting
    someone select a document they can already retrieve from
    elsewhere (Ask AI) is exactly the point.
    """

    documents = get_accessible_documents(request.user).select_related("user")

    q = request.GET.get("q", "").strip()
    if q:
        documents = documents.filter(title__icontains=q)

    file_type = request.GET.get("file_type", "").strip()
    if file_type:
        documents = documents.filter(file_type__iexact=file_type)

    documents = documents.order_by("title")

    paginator = Paginator(documents, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    def owner_badge(doc):
        if doc.user_id == request.user.id:
            return "Mine"
        if doc.is_org_library:
            return "Org"
        return "Shared"

    return JsonResponse({
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


@permission_required("pages.documents")
def document_download(request, doc_id):
    """
    Authenticated, access-checked document file access - replaces the
    raw {{ item.doc.file.url }} MEDIA_URL links documents.html used to
    render directly.

    Deliberately widened (Enterprise Document Center) from strictly
    owner-only to the requester's full accessible set - owned +
    Organization Library + shared-with-them (see
    document_access_service.get_accessible_document_ids) - since a
    sharee or org-library viewer needs to actually be able to open a
    document that's been made available to them. This reverses the
    stricter owner-only scoping this view had earlier in the same
    project history, now that there's a real, RBAC-governed mechanism
    (DocumentShare / is_org_library) for cross-user access instead of
    no mechanism at all. `?download=1` forces a Content-Disposition
    attachment instead of inline viewing, matching the two toolbar
    actions (Open/Download) documents.html offers.
    """

    document = get_object_or_404(Document, id=doc_id, id__in=get_accessible_document_ids(request.user))

    if not document.file:
        raise Http404("File not found.")

    as_attachment = request.GET.get("download") == "1"
    filename = os.path.basename(document.file.name)

    if as_attachment:
        log_activity(
            actor=request.user,
            action="document.downloaded",
            description=f'"{document.title}" downloaded by {request.user.username}',
            request=request,
        )

    return FileResponse(
        document.file.open("rb"),
        as_attachment=as_attachment,
        filename=filename,
    )


@permission_required("pages.documents")
def document_embed(request, doc_id):
    """
    Triggers processing (extract/chunk/embed/graph-enrich) for one
    PENDING or previously-FAILED document - the explicit, per-document
    counterpart to what upload_document() used to run automatically at
    upload time. Dispatches to the background thread pool
    (RAG.services.task_runner) when settings.ENABLE_ASYNC_PROCESSING is
    on, so this request returns immediately and documents.html's
    per-row progress bar polls document_status below; otherwise runs
    inline and blocks only this one request until done (same as the
    pre-Sprint-10 default).
    """

    if request.method != "POST":
        return redirect("documents")

    document = get_object_or_404(Document, id=doc_id, user=request.user)

    # process_uploaded_document() has no "clear existing chunks first"
    # step - nothing before this needed one, since it only ever ran
    # once per document. Re-running it on an already-PROCESSING or
    # already-COMPLETED document would create duplicate chunks rather
    # than actually re-processing anything, so only PENDING/FAILED are
    # allowed through (the only states the template even renders an
    # Embed/Retry button for - this is the server-side backstop).
    if document.processing_status not in (
        Document.ProcessingStatus.PENDING,
        Document.ProcessingStatus.FAILED,
    ):
        messages.error(request, f'"{document.title}" has already been processed.')
        return redirect("documents")

    if settings.ENABLE_ASYNC_PROCESSING:

        from .services import task_runner
        from .tasks import process_document_task

        try:
            task_runner.submit(process_document_task, document.id)
            messages.success(request, f'"{document.title}" is processing in the background.')
        except Exception:
            # Submitting to the in-process thread pool has no
            # network/broker to fail on, but this stays defensive - and
            # unlike AI Tasks, there's already a working inline path
            # right below (the `else` branch this mirrors), so fall
            # back to running it synchronously right here instead of
            # just showing an error. The document still gets
            # processed, just not in the background for this one
            # request.
            logger.exception("[INFRA] document_embed: background dispatch failed for document %s, falling back to inline processing", document.id)
            try:
                process_uploaded_document(document)
                messages.success(request, f'"{document.title}" processed (background dispatch failed, so this ran immediately instead).')
            except Exception:
                messages.error(request, f'Processing "{document.title}" failed - check the server logs.')

    else:

        try:
            process_uploaded_document(document)
            messages.success(request, f'"{document.title}" processed.')
        except Exception:
            messages.error(request, f'Processing "{document.title}" failed - check the server logs.')

    return redirect("documents")


@permission_required("pages.documents")
def document_status(request, doc_id):
    """
    JSON status for one document - polled by documents.html's per-row
    progress bar (Alpine.js fetch loop, no full-page reload) while a
    document is PROCESSING. embedded_count/percent are computed the
    same way documents_view's own status column is, so the two never
    disagree.
    """

    document = get_object_or_404(Document, id=doc_id, user=request.user)

    embedded_count = document.chunks.filter(vector__isnull=False).count()
    percent = round((embedded_count / document.chunk_count) * 100) if document.chunk_count else 0

    return JsonResponse({
        "status": document.processing_status,
        "chunk_count": document.chunk_count,
        "embedded_count": embedded_count,
        "percent": percent,
    })


@permission_required("pages.ask_ai")
def search_history(request):

    logs = QueryLog.objects.filter(
        user=request.user
    ).order_by("-created_at")

    history_rows = [
        {
            "log": log,
            "documents_used": sorted({
                source.get("document")
                for source in (log.sources or [])
                if source.get("document")
            }),
            "answered": not is_not_found_answer(log.answer),
        }
        for log in logs
    ]

    paginator = Paginator(history_rows, 15)

    page_number = request.GET.get("page")

    page_obj = paginator.get_page(page_number)

    return render(
        request,
        "search_history.html",
        {
            "page_obj": page_obj,
        },
    )


@permission_required("pages.analytics")
def analytics_view(request):

    data = get_analytics_data(request.user)

    # "analytics.view_all" (defined in seed_rbac.py, previously unused)
    # is exactly the permission this needs: without it, a regular user
    # sees only their own AI performance data, matching the per-user
    # scoping get_analytics_data() above already applies to the rest of
    # this page - not everyone's aggregate LLM latency/token/provider
    # stats.
    can_view_all = user_has_permission(request.user, "analytics.view_all")
    ai_performance = observability_service.get_performance_summary(
        {} if can_view_all else {"user_id": request.user.id}
    )

    return render(
        request,
        "analytics.html",
        {
            "data": data,
            "ai_performance": ai_performance,
            "document_types": get_document_type_breakdown(request.user),
        },
    )


def _save_extended_profile_fields(profile, target_user, post):
    """
    Shared by profile_view (self-service) and admin_user_profile_view
    (Admin-edit) so the two forms can never drift into saving different
    subsets of UserProfile - one implementation, two callers, same
    pattern profile_completion_service.get_completion() already follows.
    """

    profile.headline = post.get("headline", "").strip()[:150]
    profile.phone = post.get("phone", "").strip()
    profile.department = post.get("department", "").strip()
    profile.job_title = post.get("job_title", "").strip()
    profile.employee_id = post.get("employee_id", "").strip()
    profile.team = post.get("team", "").strip()
    profile.location = post.get("location", "").strip()
    profile.timezone = post.get("timezone", "").strip()
    profile.language = post.get("language", "en").strip() or "en"
    profile.linkedin_url = post.get("linkedin_url", "").strip()
    profile.github_url = post.get("github_url", "").strip()
    profile.portfolio_url = post.get("portfolio_url", "").strip()
    profile.profile_visibility = post.get("profile_visibility") or UserProfile.Visibility.PRIVATE

    manager_id = post.get("manager_id", "").strip()
    if manager_id.isdigit() and int(manager_id) != target_user.id:
        profile.manager_id = int(manager_id)
    else:
        profile.manager_id = None

    profile.skills = [s.strip() for s in post.getlist("skills") if s.strip()][:30]
    profile.certifications = [c.strip() for c in post.getlist("certifications") if c.strip()][:30]

    profile.save()


def _profile_context(user, current_session_key=None):
    """
    Real, freshly-computed data for one profile page - shared shape
    between the self-service Profile page and the Admin User Management
    profile view, so both render from the exact same backend facts.
    """

    profile, _ = UserProfile.objects.get_or_create(user=user)

    return {
        "profile_user": user,
        "profile": profile,
        "completion": get_completion(user, profile),
        "activity_summary": get_activity_summary(user),
        "login_history": device_intelligence_service.get_login_history(user),
        "active_sessions": device_intelligence_service.get_active_sessions(user, current_session_key),
        "is_online": device_intelligence_service.is_online(user),
        "account_health": device_intelligence_service.get_account_health(user),
        "last_active": device_intelligence_service.get_last_active(user),
        "manager_options": User.objects.exclude(id=user.id).order_by("username"),
        "timezone_choices": UserProfile.COMMON_TIMEZONES,
        "language_choices": UserProfile.LANGUAGE_CHOICES,
        "visibility_choices": UserProfile.Visibility.choices,
        "notification_preferences": notification_service.get_or_create_preferences(user),
    }


# Categories a user can opt out of *email* delivery for - "account"/
# "security" are deliberately excluded (see notification_service.
# ALWAYS_EMAIL_CATEGORIES), so they're never rendered as a checkbox
# here in the first place.
TOGGLEABLE_EMAIL_CATEGORIES = [
    ("document", "Document activity", "Shared documents and access changes."),
    ("ai_task", "AI Tasks", "When a run completes or fails."),
    ("system", "System announcements", "Workspace-wide announcements from an administrator."),
]


@login_required
def profile_view(request):

    password_form = PasswordChangeForm(request.user)
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":

        form_name = request.POST.get("form")

        if form_name == "profile":

            user = request.user

            user.first_name = request.POST.get("first_name", "").strip()
            user.last_name = request.POST.get("last_name", "").strip()
            user.email = request.POST.get("email", "").strip()
            user.save()

            log_activity(actor=user, action="profile.updated", description=f"{user.username} updated their personal information", request=request)

            messages.success(request, "Profile updated.")

            return redirect("profile")

        elif form_name == "extended":

            _save_extended_profile_fields(profile, request.user, request.POST)

            log_activity(actor=request.user, action="profile.updated", description=f"{request.user.username} updated their profile details", request=request)

            messages.success(request, "Profile details updated.")

            return redirect("profile")

        elif form_name == "avatar":

            if "avatar" in request.FILES:
                profile.avatar = request.FILES["avatar"]
                profile.save(update_fields=["avatar", "updated_at"])

                log_activity(actor=request.user, action="profile.updated", description=f"{request.user.username} updated their profile photo", request=request)

                messages.success(request, "Profile photo updated.")

            return redirect("profile")

        elif form_name == "notifications":

            preferences = notification_service.get_or_create_preferences(request.user)
            toggleable = {key for key, _, _ in TOGGLEABLE_EMAIL_CATEGORIES}
            enabled = set(request.POST.getlist("email_categories")) & toggleable
            preferences.disabled_email_categories = sorted(toggleable - enabled)
            preferences.save(update_fields=["disabled_email_categories", "updated_at"])

            messages.success(request, "Notification preferences updated.")

            return redirect("profile")

        elif form_name == "password":

            password_form = PasswordChangeForm(request.user, request.POST)

            if password_form.is_valid():

                user = password_form.save()

                update_session_auth_hash(request, user)

                log_activity(
                    actor=user,
                    action="user.password_changed",
                    description=f"{user.username} changed their password",
                    request=request,
                )

                # Parity with the email-based reset flow
                # (RAG.auth_views.RAGPasswordResetConfirmView) - both
                # ways of changing a password notify the same way.
                notification_service.create_notification(
                    recipient=user,
                    notification_type="account.password_changed",
                    title="Your password was changed",
                    message="Your password was just changed. If this wasn't you, contact support immediately.",
                )

                messages.success(request, "Password updated.")

                return redirect("profile")

            else:

                messages.error(request, "Please correct the errors below.")

    context = _profile_context(request.user, request.session.session_key)
    context["password_form"] = password_form
    context["current_device"] = device_intelligence_service.parse_device(request.META.get("HTTP_USER_AGENT", ""))
    context["toggleable_email_categories"] = TOGGLEABLE_EMAIL_CATEGORIES

    return render(request, "profile.html", context)


@permission_required("system.view_health")
def monitoring_view(request):
    """
    Admin-only system/infra monitoring - RAG pipeline configuration,
    database/pgvector status, and background task pool health. Gated
    by the "system.view_health" RBAC permission (see
    RAG/decorators.py, RAG/services/permission_service.py) rather than
    request.user.is_staff - a role's permission set can now be changed
    without touching this view.

    ?live=1 (the "Check Now" button) runs the real, live, synchronous
    per-provider check (health_service.get_health_status(live_llm_check
    =True), the same call auto-refresh used to make every 15 seconds
    before this page's Monitoring rework) instead of the free,
    usage-derived default - strictly on demand, via a real page
    load/reload so the fresh data renders through the exact same
    template path as every other view here (no separate JSON endpoint
    needed, and no risk of the "the reload re-fetches with the old
    default and throws the live result away" bug that shape would have
    had).
    """

    live_llm_check = request.GET.get("live") == "1"

    system_status = get_system_status()
    health = get_health_status(live_llm_check=live_llm_check)

    uptime_seconds = health["uptime_seconds"]
    days, remainder = divmod(uptime_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, _ = divmod(remainder, 60)
    uptime_display = (f"{days}d " if days else "") + f"{hours}h {minutes}m"

    return render(
        request,
        "monitoring.html",
        {
            "status": system_status,
            "health": health,
            "chunk_size": settings.CHUNK_SIZE,
            "chunk_overlap": settings.CHUNK_OVERLAP,
            "top_k": settings.TOP_K,
            "django_version": django.get_version(),
            "uptime_display": uptime_display,
        },
    )


_ACTIVITY_ICONS = {
    "document.uploaded": "file-up",
    "document.deleted": "trash-2",
    "document.downloaded": "download",
    "user.suspended": "user-x",
    "user.reactivated": "user-check",
    "user.deleted": "user-minus",
    "user.role_changed": "shield",
    "user.login": "log-in",
    "user.logout": "log-out",
    "ai_task.created": "sparkles",
    "ai_task.deleted": "trash-2",
}

# Visual category per action codename - drives the Activity tab's badge
# color the same way trace/error-group status already gets one. Anything
# not listed (a future ActivityLog action) falls back to "neutral" rather
# than erroring, so a new action codename needs no template change.
_ACTIVITY_CATEGORY = {
    "document.uploaded": "success",
    "document.downloaded": "neutral",
    "user.reactivated": "success",
    "user.login": "success",
    "user.logout": "neutral",
    "document.deleted": "danger",
    "user.suspended": "danger",
    "user.deleted": "danger",
    "user.role_changed": "warning",
    "ai_task.created": "neutral",
    "ai_task.deleted": "danger",
}


def _format_location(city, region, country):
    """Renders whatever subset of city/region/country is known as one display string, e.g. "San Francisco, CA, United States" - never raises on missing parts."""

    parts = [p for p in (city, region, country) if p]
    return ", ".join(parts) if parts else ""


def _build_activity_events(filters: dict, include_location: bool = True):
    """
    Merges Document uploads + ActivityLog rows into one workspace-wide
    feed (same two-source merge admin_system_logs_view's predecessor,
    admin_activity_logs_view, always did), now filtered by type/actor/
    text/date range/location before capping - see the docstring on the
    caller for why each source is capped independently rather than a DB
    UNION. Document uploads have no IP/location captured (upload_service
    isn't request-scoped), so those events always show "—" for it.

    include_location=False (the caller's request lacks
    "activity.view_ip_location") scrubs ip_address/location from every
    event and ignores any submitted location filter server-side, rather
    than trusting the template to just not render the column - the same
    "scrub the data, don't just hide it" rule queries.view_content
    already applies to question/answer text.
    """

    events = []

    if not filters.get("type") or filters["type"] == "document.uploaded":
        doc_qs = Document.objects.select_related("user").order_by("-uploaded_at")
        if filters.get("actor"):
            doc_qs = doc_qs.filter(user__username__icontains=filters["actor"])
        if filters.get("q"):
            doc_qs = doc_qs.filter(title__icontains=filters["q"])
        if filters.get("date_from"):
            doc_qs = doc_qs.filter(uploaded_at__date__gte=filters["date_from"])
        if filters.get("date_to"):
            doc_qs = doc_qs.filter(uploaded_at__date__lte=filters["date_to"])

        # Location has no meaning for a document upload row (no
        # IP is captured for that source) - a location filter should
        # exclude these rows rather than silently ignore the filter.
        if not (include_location and filters.get("location")):
            for doc in doc_qs[:300]:
                events.append({
                    "icon": "file-up",
                    "category": "success",
                    "type": "document.uploaded",
                    "actor": doc.user.username,
                    "text": f'"{doc.title}" uploaded',
                    "at": doc.uploaded_at,
                    "ip_address": None,
                    "location": "",
                })

    if filters.get("type", "") != "document.uploaded":
        log_qs = ActivityLog.objects.select_related("actor").order_by("-created_at")
        if filters.get("type"):
            log_qs = log_qs.filter(action=filters["type"])
        if filters.get("actor"):
            log_qs = log_qs.filter(actor__username__icontains=filters["actor"])
        if filters.get("q"):
            log_qs = log_qs.filter(description__icontains=filters["q"])
        if filters.get("date_from"):
            log_qs = log_qs.filter(created_at__date__gte=filters["date_from"])
        if filters.get("date_to"):
            log_qs = log_qs.filter(created_at__date__lte=filters["date_to"])
        if include_location and filters.get("location"):
            loc = filters["location"]
            log_qs = log_qs.filter(
                Q(ip_address__icontains=loc)
                | Q(city__icontains=loc)
                | Q(region__icontains=loc)
                | Q(country__icontains=loc)
                | Q(country_code__iexact=loc)
            )

        for log in log_qs[:300]:
            events.append({
                "icon": _ACTIVITY_ICONS.get(log.action, "activity"),
                "category": _ACTIVITY_CATEGORY.get(log.action, "neutral"),
                "type": log.action,
                "actor": log.actor.username if log.actor else "system",
                "text": log.description,
                "at": log.created_at,
                "ip_address": log.ip_address if include_location else None,
                "location": _format_location(log.city, log.region, log.country) if include_location else "",
            })

    events.sort(key=lambda event: event["at"], reverse=True)
    return events


@system_logs_access_required
def admin_system_logs_view(request):
    """
    Admin > System Logs - the one consolidated logs surface behind a
    single nav entry, replacing three previously separate pages (AI
    Logs, its Error Groups tab, and Activity Logs). Three tabs, each
    still scoped by its own permission and computed independently so a
    role holding only one of {"system.view_ai_logs", "activity.view_all_logs"}
    (system_logs_access_required's coarse view gate) only ever sees data
    for the tab(s) it's actually entitled to, the same "coarse gate +
    fine-grained internal scoping" pattern admin_settings_view uses for
    its field-group cards:

    - Request Traces - AIRequestTrace explorer (see
      RAG.services.observability_service.save_trace()).
    - Error Groups - deduped app-wide error feed (see
      RAG.services.error_intelligence_service).
    - Activity - workspace-wide audit feed (uploads, deletions,
      suspensions, role changes, logins).

    Each tab's filters/pagination use their own prefixed query params
    (none/eg_/act_) so all three can coexist in one URL without
    colliding, and so a link can deep-link straight to a given tab with
    its own filters pre-applied (e.g. Monitoring's recent-errors panel
    linking straight into a filtered Error Groups tab).
    """

    can_view_traces = user_has_permission(request.user, "system.view_ai_logs")
    can_view_activity = user_has_permission(request.user, "activity.view_all_logs")
    can_view_activity_location = can_view_activity and user_has_permission(request.user, "activity.view_ip_location")

    context = {
        "can_view_traces": can_view_traces,
        "can_view_activity": can_view_activity,
        "can_view_activity_location": can_view_activity_location,
    }

    if can_view_traces:
        filters = {
            "source": request.GET.get("source", ""),
            "provider": request.GET.get("provider", ""),
            "model": request.GET.get("model", ""),
            "status": request.GET.get("status", ""),
            "error_type": request.GET.get("error_type", ""),
            "date_from": request.GET.get("date_from", ""),
            "date_to": request.GET.get("date_to", ""),
            "trace_id": request.GET.get("trace_id", ""),
        }

        try:
            page = max(1, int(request.GET.get("page", 1)))
        except ValueError:
            page = 1

        listing = observability_service.list_traces(filters, page_size=25, page=page)

        summary = AIRequestTrace.objects.aggregate(
            total=Count("id"),
            failed=Count("id", filter=Q(status=AIRequestTrace.Status.FAILED)),
            ask_ai=Count("id", filter=Q(source=AIRequestTrace.Source.ASK_AI)),
            ai_task=Count("id", filter=Q(source=AIRequestTrace.Source.AI_TASK)),
        )

        # Pending/running AI Task runs, admin-wide (not scoped to
        # request.user, unlike ai_task_status/ai_task_results) - the one
        # gap AIRequestTrace can't fill on its own: save_trace() for a
        # run only happens after execute_run() finishes (see
        # RAG.tasks.run_ai_task), so a run stuck at PENDING (e.g. the
        # process restarted mid-task, orphaning it) never produces a
        # trace row and is otherwise invisible here.
        active_ai_task_runs = list(
            AITaskRun.objects.filter(status__in=[AITaskRun.Status.PENDING, AITaskRun.Status.RUNNING])
            .select_related("user")
            .order_by("created_at")[:50]
        )

        # A run stuck at PENDING for a while almost always means the
        # process restarted mid-task and orphaned it (run_ai_task has
        # no inline fallback and nothing resumes an interrupted run
        # automatically - see RAG.views.ai_task_create's own
        # docstring) rather than one being merely slow, so this is
        # surfaced as an explicit hint rather than making an admin
        # guess from a bare "Pending" badge and a stopwatch.
        now = timezone.now()
        for run in active_ai_task_runs:
            run.stuck_pending = run.status == AITaskRun.Status.PENDING and (now - run.created_at) > timedelta(minutes=2)

        eg_filters = {
            "logger_name": request.GET.get("eg_logger", ""),
            "level": request.GET.get("eg_level", ""),
            "q": request.GET.get("eg_q", ""),
            "date_from": request.GET.get("eg_date_from", ""),
            "date_to": request.GET.get("eg_date_to", ""),
        }

        try:
            eg_page = max(1, int(request.GET.get("eg_page", 1)))
        except ValueError:
            eg_page = 1

        eg_listing = error_intelligence_service.list_error_groups(eg_filters, page_size=25, page=eg_page)

        context.update({
            "traces": listing["results"],
            "total": listing["total"],
            "page": listing["page"],
            "num_pages": listing["num_pages"],
            "filters": request.GET,
            "filter_options": observability_service.get_filter_options(),
            "summary": summary,
            "active_ai_task_runs": active_ai_task_runs,
            "error_groups": eg_listing["results"],
            "eg_total": eg_listing["total"],
            "eg_page": eg_listing["page"],
            "eg_num_pages": eg_listing["num_pages"],
            "eg_filters": eg_filters,
        })

    if can_view_activity:
        act_filters = {
            "type": request.GET.get("act_type", ""),
            "actor": request.GET.get("act_actor", ""),
            "q": request.GET.get("act_q", ""),
            "location": request.GET.get("act_location", ""),
            "date_from": request.GET.get("act_date_from", ""),
            "date_to": request.GET.get("act_date_to", ""),
        }

        try:
            act_page = max(1, int(request.GET.get("act_page", 1)))
        except ValueError:
            act_page = 1

        if not can_view_activity_location:
            act_filters["location"] = ""

        activity_events = _build_activity_events(act_filters, include_location=can_view_activity_location)
        act_paginator = Paginator(activity_events, 25)
        act_page_obj = act_paginator.get_page(act_page)

        activity_types = ["document.uploaded"] + list(
            ActivityLog.objects.order_by().values_list("action", flat=True).distinct()
        )

        act_summary = {
            "total_events": ActivityLog.objects.count(),
        }
        if can_view_activity_location:
            act_summary["tracked_ips"] = ActivityLog.objects.exclude(ip_address__isnull=True).values("ip_address").distinct().count()
            act_summary["countries"] = ActivityLog.objects.exclude(country="").values("country").distinct().count()
        act_summary["security_alerts"] = ActivityLog.objects.filter(action="security.privilege_escalation_blocked").count()

        context.update({
            "act_page_obj": act_page_obj,
            "act_filters": act_filters,
            "act_total": len(activity_events),
            "activity_types": sorted(set(activity_types)),
            "act_summary": act_summary,
        })

    # Explicit ?tab= wins; otherwise land wherever the request's own
    # filters point (e.g. a link built with eg_/act_ params), falling
    # back to whichever tab this role can actually see first.
    requested_tab = request.GET.get("tab", "")
    if requested_tab in ("traces", "errors", "activity"):
        default_tab = requested_tab
    elif can_view_traces and (any(eg_filters.values()) or "eg_page" in request.GET):
        default_tab = "errors"
    elif can_view_activity and (any(act_filters.values()) or "act_page" in request.GET) and not can_view_traces:
        default_tab = "activity"
    elif can_view_traces:
        default_tab = "traces"
    else:
        default_tab = "activity"

    context["default_tab"] = default_tab

    return render(request, "admin/system_logs.html", context)


@permission_required("system.view_ai_logs")
def admin_trace_detail_view(request, trace_id):
    """JSON detail for one AIRequestTrace's full stage timeline/token/error breakdown - same fetch-on-click detail-modal pattern admin_query_detail_view already uses for Admin > Queries."""

    trace = get_object_or_404(AIRequestTrace, trace_id=trace_id)

    # Root-cause hints per stage, reusing exactly what compute_bottleneck()
    # already identified and stored - no re-derivation, just tagging each
    # recorded stage as "bottleneck" (it's a member of the winning
    # STAGE_GROUPS bucket) and/or "retry" (an LLM Generation stage on a
    # request that actually retried/fell back across providers), so the
    # detail modal can show a ✓/⚠ per stage instead of a flat duration list.
    bottleneck_members = observability_service.STAGE_GROUPS.get(trace.bottleneck_stage, set())
    llm_stage_members = observability_service.STAGE_GROUPS.get("LLM Generation", set())
    had_fallback_or_retry = trace.retry_count > 0 or len(trace.providers_attempted or []) > 1

    stages = []
    for stage in (trace.stages or []):
        tags = []
        if trace.bottleneck_stage and stage["name"] in bottleneck_members:
            tags.append("bottleneck")
        if had_fallback_or_retry and stage["name"] in llm_stage_members:
            tags.append("retry")
        stages.append({**stage, "tags": tags})

    return JsonResponse({
        "trace_id": trace.trace_id,
        "source": trace.get_source_display(),
        "status": trace.status,
        "user": trace.user.username if trace.user else None,
        "provider": trace.provider,
        "model": trace.model,
        "providers_attempted": trace.providers_attempted,
        "retry_count": trace.retry_count,
        "prompt_tokens": trace.prompt_tokens,
        "completion_tokens": trace.completion_tokens,
        "total_tokens": trace.total_tokens,
        "llm_latency_ms": trace.llm_latency_ms,
        "time_to_first_token_ms": trace.time_to_first_token_ms,
        "retrieved_chunks": trace.retrieved_chunks,
        "citation_count": trace.citation_count,
        "cache_hit": trace.cache_hit,
        "stages": stages,
        "total_duration_ms": trace.total_duration_ms,
        "bottleneck_label": trace.bottleneck_label,
        "error_type": trace.error_type,
        "error_message": trace.error_message,
        "created_at": trace.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "query_log_id": trace.query_log_id,
        "ai_task_run_id": trace.ai_task_run_id,
    })


@permission_required("system.view_ai_logs")
def admin_error_group_detail_view(request, group_id):
    """
    JSON detail for one ErrorGroup - the redacted message plus its
    recent_occurrences, each annotated with whether a matching
    AIRequestTrace actually exists (so the modal can offer a "View
    trace" link into the existing trace detail modal instead of a dead
    trace ID). Same fetch-on-click pattern as admin_trace_detail_view.
    """

    group = get_object_or_404(ErrorGroup, id=group_id)

    occurrence_trace_ids = [o["trace_id"] for o in (group.recent_occurrences or []) if o.get("trace_id")]
    existing_trace_ids = set(
        AIRequestTrace.objects.filter(trace_id__in=occurrence_trace_ids).values_list("trace_id", flat=True)
    )

    occurrences = [
        {
            "trace_id": o.get("trace_id"),
            "timestamp": o.get("timestamp"),
            "trace_exists": o.get("trace_id") in existing_trace_ids,
        }
        for o in reversed(group.recent_occurrences or [])
    ]

    return JsonResponse({
        "id": group.id,
        "logger_name": group.logger_name,
        "level": group.level,
        "error_type": group.error_type,
        "message": group.message,
        "occurrence_count": group.occurrence_count,
        "severity": group.severity,
        "first_seen": group.first_seen.strftime("%Y-%m-%d %H:%M:%S"),
        "last_seen": group.last_seen.strftime("%Y-%m-%d %H:%M:%S"),
        "occurrences": occurrences,
    })


@permission_required("users.view_all")
def admin_users_view(request):
    """
    Admin > Users - list every user with their assigned role and
    status, and handle suspend/activate/delete/assign-role actions.
    Metadata-only, per the RBAC scope decision: this never exposes
    another user's document content or Q&A answers, only account-level
    info (username, email, role, active status, join date).

    Every mutating action below is a privilege-escalation choke point,
    not just a permission check - see the "Privilege-escalation
    guards" section of permission_service.py for the invariants
    (only Admin can touch an Admin account or grant the Admin role;
    nobody can grant more power than they hold; the last Admin can
    never be removed) and RAG/admin.py for the same guards applied to
    the Django Admin surface, so neither can be used to bypass the
    other.
    """

    if request.method == "POST":

        action = request.POST.get("action")
        target_user = get_object_or_404(User, id=request.POST.get("user_id"))

        # "users.view_all" (checked by the decorator above) only grants
        # read access to this page - each mutating action re-checks its
        # own, more specific permission, so a future role that can view
        # the user list without being able to suspend/delete/reassign
        # is expressible without touching this view.
        if action in ("suspend", "activate") and not user_has_permission(request.user, "users.suspend"):
            messages.error(request, "You don't have permission to suspend/activate users.")

        elif action == "delete" and not user_has_permission(request.user, "users.delete"):
            messages.error(request, "You don't have permission to delete users.")

        elif action == "assign_role" and not user_has_permission(request.user, "users.assign_role"):
            messages.error(request, "You don't have permission to assign roles.")

        elif action in ("suspend", "activate", "delete", "assign_role") and not can_actor_manage_target_user(request.user, target_user):
            log_activity(
                actor=request.user,
                action="security.privilege_escalation_blocked",
                description=f'{request.user.username} tried to {action} "{target_user.username}" (more privileged account) - blocked',
                request=request,
            )
            messages.error(request, "You don't have permission to manage this account.")

        elif action == "suspend":
            if target_user == request.user:
                messages.error(request, "You can't suspend your own account.")
            elif is_last_admin(target_user):
                messages.error(request, "You can't suspend the last remaining Admin.")
            else:
                target_user.is_active = False
                target_user.save(update_fields=["is_active"])
                log_activity(
                    actor=request.user,
                    action="user.suspended",
                    description=f'"{target_user.username}" suspended by {request.user.username}',
                    request=request,
                )
                # "security" category - always emailed regardless of
                # the target's notification preferences (see
                # notification_service.ALWAYS_EMAIL_CATEGORIES), same
                # as the account.password_changed notification.
                notification_service.create_notification(
                    recipient=target_user,
                    actor=request.user,
                    notification_type="security.account_suspended",
                    title="Your account has been suspended",
                    message="Your account was suspended by an administrator. Contact support if you believe this is a mistake.",
                )
                messages.success(request, f'"{target_user.username}" suspended.')

        elif action == "activate":
            target_user.is_active = True
            target_user.save(update_fields=["is_active"])
            log_activity(
                actor=request.user,
                action="user.reactivated",
                description=f'"{target_user.username}" reactivated by {request.user.username}',
                request=request,
            )
            notification_service.create_notification(
                recipient=target_user,
                actor=request.user,
                notification_type="security.account_reactivated",
                title="Your account has been reactivated",
                message="Your account is active again - you can now log in normally.",
            )
            messages.success(request, f'"{target_user.username}" reactivated.')

        elif action == "delete":
            if target_user == request.user:
                messages.error(request, "You can't delete your own account.")
            elif is_last_admin(target_user):
                messages.error(request, "You can't delete the last remaining Admin.")
            else:
                deleted_username = target_user.username
                deleted_email = target_user.email
                target_user.delete()
                log_activity(
                    actor=request.user,
                    action="user.deleted",
                    description=f'"{deleted_username}" deleted by {request.user.username}',
                    request=request,
                )
                # No User row survives to attach an in-app Notification
                # to (Notification.recipient is a required FK) - the
                # email is captured before delete() and sent directly,
                # same pattern as the document-share invite email.
                if deleted_email:
                    from .services import task_runner
                    from .tasks import send_account_deleted_email_task
                    task_runner.submit(send_account_deleted_email_task, deleted_email, deleted_username)
                messages.success(request, "User deleted.")

        elif action == "assign_role":

            role_slug = request.POST.get("role")
            role = get_object_or_404(Role, slug=role_slug)

            if not can_actor_assign_role(request.user, role):
                log_activity(
                    actor=request.user,
                    action="security.privilege_escalation_blocked",
                    description=f'{request.user.username} tried to assign "{role.name}" to "{target_user.username}" (exceeds their own permissions) - blocked',
                    request=request,
                )
                messages.error(request, f'You don\'t have permission to assign the "{role.name}" role.')
            elif role.slug != ADMIN_ROLE_SLUG and is_last_admin(target_user):
                messages.error(request, "You can't move the last remaining Admin out of the Admin role.")
            else:
                UserRole.objects.update_or_create(
                    user=target_user,
                    defaults={"role": role, "assigned_by": request.user},
                )
                log_activity(
                    actor=request.user,
                    action="user.role_changed",
                    description=f'"{target_user.username}" set to {role.name} by {request.user.username}',
                    request=request,
                )
                notification_service.create_notification(
                    recipient=target_user,
                    actor=request.user,
                    notification_type="account.role_changed",
                    title="Your role has changed",
                    message=f'Your role was changed to "{role.name}".',
                )
                messages.success(request, f'"{target_user.username}" is now {role.name}.')

        return redirect("admin_users")

    users_list = (
        User.objects.select_related("role_assignment__role")
        .order_by("-date_joined")
    )

    admin_role = Role.objects.filter(slug=ADMIN_ROLE_SLUG).first()
    assignable_roles = get_assignable_roles(request.user)

    return render(
        request,
        "admin/users.html",
        {
            "users_list": users_list,
            "assignable_roles": assignable_roles,
            "assignable_role_ids": {role.id for role in assignable_roles},
            "admin_role_id": admin_role.id if admin_role else None,
        },
    )


@permission_required("users.view_all")
def admin_user_profile_view(request, user_id):
    """
    Admin > Users > (a user's) Profile - the full enterprise profile
    (completion score, activity summary, login/device history,
    role/permissions, account health) for any one user, editable by an
    Admin per the confirmed scope (see PROFILE_MODULE plan). Gated by
    the same "users.view_all" permission that already guards the Users
    list, plus its own privilege-escalation guard on the mutating path
    below - viewing an Admin's profile is fine for anyone who can reach
    this page at all, but editing one is not, mirroring
    can_actor_manage_target_user's use throughout admin_users_view.

    Login history / device / IP-location are additionally gated inline
    by the target's own "activity.view_all_logs" / "activity.view_ip_location"
    permissions on the VIEWING admin's role - same coarse+fine pattern
    admin_system_logs_view already uses, so a role holding only
    "users.view_all" sees the profile but not another user's IP/location.
    """

    target_user = get_object_or_404(User, id=user_id)

    can_view_activity = user_has_permission(request.user, "activity.view_all_logs")
    can_view_location = can_view_activity and user_has_permission(request.user, "activity.view_ip_location")

    if request.method == "POST":

        if not can_actor_manage_target_user(request.user, target_user):
            log_activity(
                actor=request.user,
                action="security.privilege_escalation_blocked",
                description=f'{request.user.username} tried to edit "{target_user.username}"\'s profile (more privileged account) - blocked',
                request=request,
            )
            messages.error(request, "You don't have permission to edit this account.")
        else:
            profile, _ = UserProfile.objects.get_or_create(user=target_user)
            _save_extended_profile_fields(profile, target_user, request.POST)

            log_activity(
                actor=request.user,
                action="user.profile_updated_by_admin",
                description=f'{request.user.username} updated "{target_user.username}"\'s profile',
                request=request,
            )

            messages.success(request, f'"{target_user.username}"\'s profile updated.')

        return redirect("admin_user_profile", user_id=target_user.id)

    context = _profile_context(target_user)
    context.update({
        "can_view_activity": can_view_activity,
        "can_view_location": can_view_location,
        "login_history": context["login_history"] if can_view_activity else [],
        "assigned_role": getattr(target_user, "role_assignment", None),
        "target_permission_set": sorted(get_user_permission_set(target_user)),
        "can_edit": can_actor_manage_target_user(request.user, target_user),
        "breadcrumb_leaf": target_user.get_full_name() or target_user.username,
    })
    if not can_view_location:
        for entry in context["login_history"]:
            entry["ip_address"] = None
            entry["location"] = ""

    return render(request, "admin/user_profile.html", context)


@permission_required("roles.manage")
def admin_roles_view(request):
    """
    Admin > Roles - define what each Role can do (create a role, set
    which Permissions it grants). Gated by the "roles.manage"
    permission (granted to Admin by default, like every permission -
    see Role.has_permission's bypass in RAG/models.py) rather than a
    hardcoded Super Admin tier, which no longer exists: this is what
    makes "future roles added without touching code" concretely true -
    creating a Manager/HR/Auditor role and choosing its permissions
    happens entirely here, and a custom role can itself be granted
    "roles.manage" to administer roles without being Admin.
    """

    if request.method == "POST":

        action = request.POST.get("action")

        if action == "create_role":

            name = request.POST.get("name", "").strip()
            slug = slugify(name)

            if not name or not slug:
                messages.error(request, "Role name is required.")
            elif Role.objects.filter(slug=slug).exists():
                messages.error(request, f'A role named "{name}" already exists.')
            else:
                Role.objects.create(
                    name=name,
                    slug=slug,
                    description=request.POST.get("description", "").strip(),
                )
                log_activity(
                    actor=request.user,
                    action="role.created",
                    description=f'Role "{name}" created by {request.user.username}',
                    request=request,
                )
                messages.success(request, f'Role "{name}" created.')

        elif action == "update_permissions":

            role = get_object_or_404(Role, id=request.POST.get("role_id"))

            if role.slug == ADMIN_ROLE_SLUG:
                # Admin always has every permission by design (see
                # Role.has_permission) - refuse the edit outright
                # rather than silently accepting a subset that would
                # never actually take effect.
                messages.error(request, "The Admin role always has full access and can't be edited.")
            else:
                selected_codenames = set(request.POST.getlist("permissions"))

                if not is_admin(request.user):
                    current = set(role.permissions.values_list("codename", flat=True))
                    attempted_escalation = (selected_codenames - get_user_permission_set(request.user)) - current
                    if attempted_escalation:
                        log_activity(
                            actor=request.user,
                            action="security.privilege_escalation_blocked",
                            description=(
                                f'{request.user.username} tried to grant "{role.name}" permissions beyond their '
                                f'own ({", ".join(sorted(attempted_escalation))}) - blocked'
                            ),
                            request=request,
                        )

                updated_codenames = compute_updated_role_permissions(request.user, role, selected_codenames)
                role.permissions.set(Permission.objects.filter(codename__in=updated_codenames))
                log_activity(
                    actor=request.user,
                    action="role.permissions_updated",
                    description=f'Permissions updated for "{role.name}" by {request.user.username}',
                    request=request,
                )
                messages.success(request, f'Permissions updated for "{role.name}".')

        elif action == "delete_role":

            role = get_object_or_404(Role, id=request.POST.get("role_id"))
            role_permissions = set(role.permissions.values_list("codename", flat=True))

            if role.is_system:
                messages.error(request, f'"{role.name}" is a built-in role and can\'t be deleted.')
            elif role.user_assignments.exists():
                messages.error(
                    request,
                    f'"{role.name}" is still assigned to {role.user_assignments.count()} user(s) - reassign them first.',
                )
            elif not is_admin(request.user) and not role_permissions.issubset(get_user_permission_set(request.user)):
                log_activity(
                    actor=request.user,
                    action="security.privilege_escalation_blocked",
                    description=f'{request.user.username} tried to delete "{role.name}" (grants access beyond their own) - blocked',
                    request=request,
                )
                messages.error(request, f'You don\'t have permission to delete "{role.name}" - it grants access beyond your own.')
            else:
                role_name = role.name
                role.delete()
                log_activity(
                    actor=request.user,
                    action="role.deleted",
                    description=f'Role "{role_name}" deleted by {request.user.username}',
                    request=request,
                )
                messages.success(request, f'Role "{role_name}" deleted.')

        return redirect("admin_roles")

    actor_is_admin = is_admin(request.user)
    actor_perms = get_user_permission_set(request.user)

    # A non-Admin "roles.manage" holder only ever sees, and can only
    # ever grant, permissions within their own scope (see
    # compute_updated_role_permissions) - modules/checkboxes outside
    # that scope are hidden entirely rather than shown disabled, same
    # "hide, don't disable" rule the nav templates already follow.
    permission_modules = []
    for module in get_permission_modules():
        visible_permissions = module["permissions"] if actor_is_admin else [
            p for p in module["permissions"] if p.codename in actor_perms
        ]
        if not visible_permissions:
            continue
        permission_modules.append({
            **module,
            "permissions": visible_permissions,
            "hidden_count": len(module["permissions"]) - len(visible_permissions),
            "codenames_json": json.dumps([p.codename for p in visible_permissions]),
        })

    total_permission_count = sum(len(module["permissions"]) for module in permission_modules)

    roles_data = []
    for role in Role.objects.prefetch_related("permissions").order_by("name"):
        role_granted = set(role.permissions.values_list("codename", flat=True))
        visible_granted = role_granted if actor_is_admin else (role_granted & actor_perms)
        roles_data.append({
            "role": role,
            "granted_json": json.dumps(sorted(visible_granted)),
            "hidden_granted_count": len(role_granted - visible_granted),
        })

    return render(
        request,
        "admin/roles.html",
        {
            "roles_data": roles_data,
            "permission_modules": permission_modules,
            "total_permission_count": total_permission_count,
            "sensitive_permissions": SENSITIVE_PERMISSIONS,
        },
    )


@settings_access_required
def admin_settings_view(request):
    """
    Admin > Settings - live-editable RAG pipeline configuration: LLM
    provider, retrieval top-K/answer temperature, chunk size/overlap,
    and the Sprint 6-8 retrieval toggles (query expansion, HyDE,
    multi-query, dynamic top-K, reranker, context compression). Saved
    values are applied to the running process immediately (and to
    every other worker process within a short delay - see
    RAG.middleware.SystemConfigSyncMiddleware) without a redeploy.

    Embedding model, database connection, and API keys are shown
    read-only, not because they're unbuilt but because making them
    live-editable here would be actively unsafe or the wrong place for
    them - see SystemConfiguration's own docstring for why each of the
    three is excluded on purpose.

    Each card is gated by its own settings.manage_* permission (checked
    both here - implicitly, via @settings_access_required allowing
    entry - and in the template via {% if "..." in user_permissions %},
    and again in system_config_service.save_config(), which only
    applies fields the submitting user actually holds permission for).
    A role holding only "settings.manage_chunking" sees only the
    Retrieval & Chunking card and can't move llm_provider or any other
    field even by hand-crafting a POST body.
    """

    config = get_config()

    if request.method == "POST":

        try:
            data = {
                "llm_provider": request.POST.get("llm_provider", config.llm_provider),
                "enable_fallback": request.POST.get("enable_fallback") == "on",
                "openrouter_model": request.POST.get("openrouter_model", config.openrouter_model).strip() or config.openrouter_model,
                "groq_model": request.POST.get("groq_model", config.groq_model).strip() or config.groq_model,
                "gemini_model": request.POST.get("gemini_model", config.gemini_model).strip() or config.gemini_model,
                "top_k": int(request.POST.get("top_k", config.top_k)),
                "answer_temperature": float(request.POST.get("answer_temperature", config.answer_temperature)),
                "chunk_size": int(request.POST.get("chunk_size", config.chunk_size)),
                "chunk_overlap": int(request.POST.get("chunk_overlap", config.chunk_overlap)),
                "enable_query_expansion": request.POST.get("enable_query_expansion") == "on",
                "enable_hyde": request.POST.get("enable_hyde") == "on",
                "enable_multi_query": request.POST.get("enable_multi_query") == "on",
                "multi_query_variants": int(request.POST.get("multi_query_variants", config.multi_query_variants)),
                "enable_dynamic_top_k": request.POST.get("enable_dynamic_top_k") == "on",
                "dynamic_top_k_max": int(request.POST.get("dynamic_top_k_max", config.dynamic_top_k_max)),
                "enable_reranker": request.POST.get("enable_reranker") == "on",
                "reranker_candidate_multiplier": int(request.POST.get("reranker_candidate_multiplier", config.reranker_candidate_multiplier)),
                "enable_context_compression": request.POST.get("enable_context_compression") == "on",
                "context_compression_threshold": float(request.POST.get("context_compression_threshold", config.context_compression_threshold)),
            }
        except (TypeError, ValueError):
            messages.error(request, "Some values were invalid - nothing was saved.")
            return redirect("admin_settings")

        try:
            save_config(data, request.user)
        except SettingsValidationError as exc:
            for error in exc.errors:
                messages.error(request, error)
            return redirect("admin_settings")

        log_activity(
            actor=request.user,
            action="settings.updated",
            description=f"RAG pipeline configuration updated by {request.user.username}",
            request=request,
        )

        messages.success(request, "Settings saved.")

        return redirect("admin_settings")

    return render(
        request,
        "admin/settings.html",
        {
            "config": config,
            "system_status": get_system_status(),
            "db_name": settings.DATABASES["default"]["NAME"],
            "db_host": settings.DATABASES["default"]["HOST"],
            "llm_provider_options": get_llm_provider_options(config),
            "can_edit_any": any(
                user_has_permission(request.user, code)
                for code in ("settings.manage_llm", "settings.manage_chunking", "settings.manage_retrieval")
            ),
        },
    )


@permission_required("settings.manage_llm")
def llm_provider_health_check(request):
    """
    Admin > Settings "Test Connection" button - runs a real minimal
    request against exactly the named provider (bypassing the fallback
    chain, since this is meant to test that one provider) and returns
    {ok, latency_ms, message} as JSON. Never a 500: an unconfigured or
    unknown provider is a normal ok=False response, not an exception.
    """

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    provider = request.POST.get("provider", "")
    result = get_llm().health_check(provider)

    return JsonResponse(result)


@permission_required("queries.view_all_logs")
def admin_queries_view(request):
    """
    Admin > Queries - a workspace-wide, searchable/filterable/sortable
    view of every user's Ask AI query log, with analytics and CSV
    export.

    Privacy boundary (unchanged from before this redesign, just more
    thoroughly enforced): "queries.view_all_logs" alone grants
    metadata only - owner, status (derived, never the raw answer
    text), search method, confidence, response time, source count,
    flagged state, timestamp. The actual question/answer content, and
    content-based search, require the further "queries.view_content"
    permission - see admin_query_detail_view, which is also the one
    place that logs an audit event each time that content is actually
    opened.
    """

    can_view_content = user_has_permission(request.user, "queries.view_content")

    params = request.GET.copy()
    params["_content_search_allowed"] = can_view_content

    logs = filter_and_sort_queries(params, request_user=request.user)
    analytics = get_queries_analytics(logs)

    paginator = Paginator(logs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))
    annotate_status(page_obj.object_list)

    return render(
        request,
        "admin/queries.html",
        {
            "page_obj": page_obj,
            "analytics": analytics,
            "search_methods": get_search_methods(),
            "can_view_content": can_view_content,
            "filters": request.GET,
        },
    )


@permission_required("queries.view_all_logs", "queries.view_content")
def admin_query_detail_view(request, log_id):
    """
    Returns one QueryLog's full content (question, answer, sources) as
    JSON, for the "View" action on Admin > Queries. The one place in
    the app an admin actually sees another user's Q&A content, so
    every call is written to the audit trail with which log was
    opened and by whom - "explicitly authorized auditing", not a
    silent read.
    """

    log = get_object_or_404(QueryLog, id=log_id)

    log_activity(
        actor=request.user,
        action="admin.query_content_viewed",
        description=f'{request.user.username} viewed the content of a query log by "{log.user.username}" (log #{log.id}) via Admin > Queries',
        request=request,
    )

    return JsonResponse({
        "id": log.id,
        "owner": log.user.username,
        "question": log.question,
        "answer": log.answer,
        "sources": log.sources,
        "search_method": log.search_method,
        "confidence": log.confidence,
        "response_time_ms": log.response_time_ms,
        "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    })


@permission_required("queries.view_all_logs")
def admin_query_toggle_flag_view(request, log_id):
    """
    Pin/unpin a query log for follow-up on Admin > Queries - a shared
    review flag visible to anyone with "queries.view_all_logs", not
    tied to one admin's own preference, so it doesn't need
    "queries.view_content" (it never touches question/answer text).
    """

    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    log = get_object_or_404(QueryLog, id=log_id)
    log.is_flagged = not log.is_flagged
    log.save(update_fields=["is_flagged"])

    return JsonResponse({"id": log.id, "is_flagged": log.is_flagged})


@permission_required("queries.view_all_logs")
def export_queries_report(request):
    """
    Admin > Queries CSV export - same filters as the on-page table, same
    content-permission gate as admin_query_detail_view. An export that
    includes Question/Answer columns is audit-logged exactly like an
    individual content view, since it's the same privacy-sensitive
    read, just in bulk.
    """

    can_view_content = user_has_permission(request.user, "queries.view_content")

    params = request.GET.copy()
    params["_content_search_allowed"] = can_view_content
    logs = filter_and_sort_queries(params, request_user=request.user).select_related("user")

    if can_view_content:
        log_activity(
            actor=request.user,
            action="admin.query_content_exported",
            description=f'{request.user.username} exported {logs.count()} query log(s) including question/answer content via Admin > Queries',
            request=request,
        )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="queries_report.csv"'

    writer = csv.writer(response)
    writer.writerow(QUERIES_REPORT_HEADER_WITH_CONTENT if can_view_content else QUERIES_REPORT_HEADER_METADATA)
    writer.writerows(get_queries_report_rows(logs, include_content=can_view_content))

    return response


@permission_required("pages.knowledge_base")
def knowledge_base_view(request):
    """
    Explore Topics: overview stats, category breakdown, and a
    filterable/searchable Topic list (entities merged across every
    document owner the viewer can access - see
    knowledge_service._build_topic_dataset). The Knowledge Center's
    other pages (Topic Detail, Relationship/Graph/Citation/Insights
    views) are reached from the tabs on this page rather than the
    sidebar, keeping the main nav to one entry per section.
    """

    # Built once and shared below - overview/insights/search_topics
    # each need "this user's visible topics/relationships", and
    # independently rebuilding it 3x per page load was the previous
    # behavior (~5 duplicate queries each).
    dataset = _build_topic_dataset(request.user)

    overview = get_knowledge_overview(request.user, dataset=dataset)

    # Reuses get_knowledge_insights() (already computed for the Insights
    # tab) rather than a second aggregation - just surfaces a couple of
    # its fields (processing status, recent activity) here too, as an
    # at-a-glance preview with a link to the full Insights tab.
    insights = get_knowledge_insights(request.user, dataset=dataset)

    query = request.GET.get("q", "").strip()
    entity_type = request.GET.get("type", "").strip()

    topics_page = search_topics(
        request.user, query=query, entity_type=entity_type, page=request.GET.get("page"), dataset=dataset
    )

    return render(
        request,
        "knowledge/browse.html",
        {
            "overview": overview,
            "insights": insights,
            "topics_page": topics_page,
            "query": query,
            "selected_type": entity_type,
        },
    )


@permission_required("pages.knowledge_base")
def entity_detail_view(request, entity_id):
    """Topic Detail - a single Topic's connected documents, teams, relationships, cross-references, timeline, and citations."""

    detail = get_topic_detail(request.user, entity_id)

    if detail is None:
        messages.error(request, "That topic couldn't be found.")
        return redirect("knowledge_base")

    return render(
        request,
        "knowledge/entity_detail.html",
        {
            **detail,
            "entity_color": get_entity_type_color(detail["entity"].entity_type),
            "breadcrumb_leaf": detail["entity"].display_name,
        },
    )


@permission_required("pages.knowledge_base")
def relationships_view(request):

    relation_type = request.GET.get("type", "").strip()

    relationships_page = get_relationships(
        request.user, relation_type=relation_type, page=request.GET.get("page")
    )

    # Annotated in Python (not a DB field) so the table's source/target
    # color dots use the exact same ENTITY_TYPE_COLORS every other
    # Knowledge Base page draws from - get_relationships() returns raw
    # Relationship rows, not the color-carrying Topic dicts browse.html
    # and the graph use.
    for rel in relationships_page:
        rel.source.color = get_entity_type_color(rel.source.entity_type)
        rel.target.color = get_entity_type_color(rel.target.entity_type)

    return render(
        request,
        "knowledge/relationships.html",
        {
            "relationships_page": relationships_page,
            "relation_types": get_relation_types(request.user),
            "selected_type": relation_type,
        },
    )


@permission_required("pages.knowledge_base")
def knowledge_graph_view(request):

    graph_data = get_graph_data(request.user)
    insights = get_graph_insights(request.user)

    # Computed for exactly the entity_type values actually present in
    # this viewer's graph (not the whole ENTITY_TYPE_COLORS dict) so a
    # free-form/custom type the LLM produced still gets a real,
    # deterministic color via get_entity_type_color()'s fallback,
    # rather than relying on vis-network's own auto-palette client-side.
    present_types = sorted({node["group"] for node in graph_data["nodes"]})
    entity_type_colors = {t: get_entity_type_color(t) for t in present_types}

    return render(
        request,
        "knowledge/graph.html",
        {
            "graph_data": graph_data,
            "insights": insights,
            "entity_type_colors": entity_type_colors,
        },
    )


@permission_required("pages.knowledge_base")
def graph_node_detail_json(request, entity_id):

    detail = get_topic_node_detail(request.user, entity_id)

    if detail is None:
        return JsonResponse({"error": "Not found"}, status=404)

    return JsonResponse(detail)


@permission_required("pages.knowledge_base")
def graph_edge_detail_json(request):

    try:
        topic_a_id = int(request.GET.get("a"))
        topic_b_id = int(request.GET.get("b"))
    except (TypeError, ValueError):
        return HttpResponseBadRequest("Query params 'a' and 'b' must be entity ids.")

    detail = get_topic_pair_relationship_detail(request.user, topic_a_id, topic_b_id)

    if detail is None:
        return JsonResponse({"error": "Not found"}, status=404)

    return JsonResponse(detail)


@permission_required("pages.knowledge_base")
def document_knowledge_view(request, doc_id):
    """
    Document Relationship View - one document's extracted topics,
    relationships, related documents (shared-topic and embedding-
    similarity based), and citation history. Gated the same way every
    other non-owner-only document view is: accessible-scoped (owned +
    Organization Library + shared-with-them), not owner-only, since
    exploring a shared/org document's knowledge is exactly what a
    sharee or org-library viewer needs to do (same rationale
    document_preview/document_download already document).
    """

    document = get_object_or_404(Document, id=doc_id, id__in=get_accessible_document_ids(request.user))

    knowledge = get_document_knowledge(request.user, document)
    is_owner = document.user_id == request.user.id

    return render(
        request,
        "knowledge/document_relationships.html",
        {
            **knowledge,
            "file_size_display": format_bytes(document.file_size),
            "is_owner": is_owner,
            # Share recipients are only shown to the owner - viewing who
            # else a document is shared with isn't something a sharee or
            # org-library viewer needs, and it's the one piece of
            # relationship data here that names other specific people.
            "shares": document.shares.select_related("shared_with_user", "shared_with_role") if is_owner else None,
            "breadcrumb_leaf": document.title,
        },
    )


@permission_required("pages.knowledge_base")
def citation_explorer_view(request):

    citations = resolve_topics_for_citations(request.user, get_citation_explorer(request.user))

    return render(
        request,
        "knowledge/citations.html",
        {
            "citations": citations,
        },
    )


@permission_required("pages.knowledge_base")
def knowledge_insights_view(request):
    """
    Knowledge Insights - read-only aggregates over the viewer's
    accessible knowledge (most-referenced documents, frequently
    connected topics, recent activity, coverage/quality gaps, possible
    duplicates). No LLM calls here - that's Document Analysis, which
    belongs to AI Tasks, not the Knowledge Center.
    """

    insights = get_knowledge_insights(request.user)

    return render(
        request,
        "knowledge/insights.html",
        {
            "insights": insights,
        },
    )


@permission_required("pages.reports")
def reports_view(request):
    """
    Reports - real per-row CSV exports (documents, usage, AI task runs,
    knowledge topics) plus a live Comparative Report: this period vs.
    the one before it across the headline usage metrics, computed on
    demand from real data (see stats_service.get_comparison_report_data)
    - not a "coming soon" placeholder, and not dependent on any
    scheduling/email infrastructure this project doesn't have.

    Each export card also shows a real trend badge (stats_service.
    get_kpi_trends, already computed for the Dashboard's KPI cards -
    reused here rather than recomputed) and, for documents, a live
    type breakdown (get_document_type_breakdown, same source as the
    Dashboard's Document Types donut) as a preview of what the export
    actually contains - not a fabricated summary.
    """

    documents = Document.objects.filter(user=request.user)

    return render(
        request,
        "reports.html",
        {
            "document_count": documents.count(),
            "total_storage": format_bytes(documents.aggregate(total=Sum("file_size"))["total"] or 0),
            "question_count": QueryLog.objects.filter(user=request.user).count(),
            "ai_task_run_count": AITaskRun.objects.filter(user=request.user).count(),
            "topic_count": get_knowledge_overview(request.user)["total_entities"],
            "comparison": get_comparison_report_data(request.user),
            "kpi_trends": get_kpi_trends(request.user),
            "document_types": get_document_type_breakdown(request.user),
        },
    )


@permission_required("pages.reports")
def export_documents_report(request):

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="documents_report.csv"'

    writer = csv.writer(response)
    writer.writerow(DOCUMENTS_REPORT_HEADER)
    writer.writerows(get_documents_report_rows(request.user))

    return response


@permission_required("pages.reports")
def export_usage_report(request):

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="usage_report.csv"'

    writer = csv.writer(response)
    writer.writerow(USAGE_REPORT_HEADER)
    writer.writerows(get_usage_report_rows(request.user))

    return response


@permission_required("pages.reports")
def export_comparison_report(request):

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="comparison_report.csv"'

    writer = csv.writer(response)
    writer.writerow(COMPARISON_REPORT_HEADER)
    writer.writerows(get_comparison_report_rows(get_comparison_report_data(request.user)))

    return response


@permission_required("pages.reports")
def export_ai_task_runs_report(request):

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="ai_task_runs_report.csv"'

    writer = csv.writer(response)
    writer.writerow(AI_TASK_RUNS_REPORT_HEADER)
    writer.writerows(get_ai_task_runs_report_rows(request.user))

    return response


@permission_required("pages.reports")
def export_knowledge_topics_report(request):

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="knowledge_topics_report.csv"'

    writer = csv.writer(response)
    writer.writerow(KNOWLEDGE_TOPICS_REPORT_HEADER)
    writer.writerows(get_knowledge_topics_report_rows(request.user))

    return response


# ==========================
# AI TASKS
# ==========================
# A guided wizard (Select Task -> Select Documents -> Configure ->
# Run -> Review -> Export) running one of AITaskRun.TaskType's 8
# generic operations over a set of selected documents. Every view here
# is scoped to user=request.user - no cross-user visibility in v1 (see
# RAG.services.ai_tasks_engine_service and the AI Tasks plan for the
# full design). All 8 task types share one engine
# (ai_tasks_engine_service.execute_run) - this module only handles
# request validation, run creation, and result presentation.

AI_TASKS_NEEDING_REFERENCE = {AITaskRun.TaskType.VALIDATE}
AI_TASKS_ALLOWING_REFERENCE = {AITaskRun.TaskType.ANALYZE, AITaskRun.TaskType.VALIDATE}


@permission_required("pages.ai_tasks")
def ai_tasks_view(request):
    """GET-only wizard shell - Select Task / Select Documents / Configure / Run are all client-side Alpine steps here; ai_task_create is what actually creates a run."""

    return render(
        request,
        "ai_tasks/wizard.html",
        {"task_types": AITaskRun.TaskType.choices, "ai_tasks_max_documents": settings.AI_TASKS_MAX_DOCUMENTS},
    )


@permission_required("pages.ai_tasks")
def ai_task_create(request):
    """
    Creates and dispatches one AITaskRun. Unlike document_embed, this
    always dispatches to the in-process background thread pool
    (RAG.services.task_runner.submit) regardless of
    settings.ENABLE_ASYNC_PROCESSING - AI Task runs have no inline
    execution path. Unlike the old Celery-based design, there's no
    missing-worker failure mode here: the pool lives in this same
    process.
    """

    if request.method != "POST":
        return redirect("ai_tasks")

    task_type = request.POST.get("task_type", "")

    if task_type not in AITaskRun.TaskType.values:
        messages.error(request, "Choose a task type.")
        return redirect("ai_tasks")

    document_ids_raw = request.POST.getlist("document_ids")
    reference_ids_raw = request.POST.getlist("reference_document_ids")

    accessible_ids = get_accessible_document_ids(request.user)

    def _valid_ids(raw_ids):
        parsed = []
        for value in raw_ids:
            if value.isdigit() and int(value) in accessible_ids:
                parsed.append(int(value))
        return parsed

    target_ids = _valid_ids(document_ids_raw)
    reference_ids = _valid_ids(reference_ids_raw) if task_type in AI_TASKS_ALLOWING_REFERENCE else []

    # Reject silently-dropped ids outright rather than just proceeding
    # with fewer documents than requested - a client-submitted id
    # outside the accessible set is either a bug or tampering, either
    # way it should not be quietly ignored.
    if len(target_ids) != len(document_ids_raw) or len(reference_ids) != len(reference_ids_raw):
        messages.error(request, "One or more selected documents are not available to you.")
        return redirect("ai_tasks")

    if not target_ids:
        messages.error(request, "Select at least one document.")
        return redirect("ai_tasks")

    if len(target_ids) > settings.AI_TASKS_MAX_DOCUMENTS:
        messages.error(
            request,
            f"You selected {len(target_ids)} documents; AI Task runs are limited to "
            f"{settings.AI_TASKS_MAX_DOCUMENTS} documents per run.",
        )
        return redirect("ai_tasks")

    if task_type in AI_TASKS_NEEDING_REFERENCE and not reference_ids:
        messages.error(request, "This task requires at least one reference document.")
        return redirect("ai_tasks")

    try:
        config = json.loads(request.POST.get("config", "") or "{}")
        if not isinstance(config, dict):
            config = {}
    except (ValueError, TypeError):
        config = {}

    run = AITaskRun.objects.create(
        user=request.user,
        task_type=task_type,
        config=config,
        document_count=len(target_ids),
    )

    AITaskRunDocument.objects.bulk_create([
        AITaskRunDocument(run=run, document_id=doc_id, role=AITaskRunDocument.Role.TARGET)
        for doc_id in target_ids
    ] + [
        AITaskRunDocument(run=run, document_id=doc_id, role=AITaskRunDocument.Role.REFERENCE)
        for doc_id in reference_ids
    ])

    log_activity(
        actor=request.user,
        action="ai_task.created",
        description=f'{request.user.username} started an AI Task ({run.get_task_type_display()}) over {len(target_ids)} document(s)',
        request=request,
    )

    from .services import task_runner
    from .tasks import run_ai_task

    try:
        task_runner.submit(run_ai_task, run.id, key=run.id)
    except Exception:
        # Submitting to the in-process thread pool has no
        # network/broker to fail on, but this stays defensive - never
        # let an unexpected failure surface as a raw 500. The run row
        # already exists, so mark it FAILED with a clear explanation
        # rather than leaving it silently stuck at PENDING forever.
        logger.exception("ai_task_create: failed to dispatch run %s to the background thread pool", run.id)
        run.status = AITaskRun.Status.FAILED
        run.error_message = "Could not start this task due to an unexpected server error. Contact your administrator."
        run.save(update_fields=["status", "error_message"])

    return redirect("ai_task_results", run_id=run.id)


@login_required
def ai_task_cancel(request, run_id):
    """
    Stops a pending/running AITaskRun. Owner or admin-area access (an
    admin clearing a run that's stuck or blocking others from Admin >
    System Logs) - everything else on this run's pages is owner-only,
    gated on the "pages.ai_tasks" permission (ai_task_status/
    ai_task_results), but an admin acting from System Logs is gated on
    "system.view_ai_logs" instead and may not hold "pages.ai_tasks" at
    all - so unlike its siblings, this view is @login_required only,
    with authorization entirely in the owner-or-admin check below.

    Sets cancel_requested=True (the cooperative stop
    ai_tasks_engine_service._call_llm_json() polls between LLM calls -
    see its docstring) and best-effort cancels the background thread
    pool task via task_runner.cancel(), which only actually prevents a
    still-*queued* run from ever starting - once a pool thread has
    picked it up, Future.cancel() can't interrupt it (the same
    real-world limitation the old Celery revoke(terminate=True) had
    without a prefork worker pool). A run that's already mid-LLM-call
    stops at the next call, not immediately - the status badge reflects
    that ("Stopping…" until it actually lands on CANCELLED).

    A COMPLETED/FAILED/CANCELLED run can't be cancelled - returns 400,
    not a silent no-op, so a stale "Stop" click (e.g. a second tab)
    surfaces as an explicit "already finished" rather than looking like
    it did something.
    """

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    run = get_object_or_404(AITaskRun, id=run_id)

    if run.user_id != request.user.id and not is_admin(request.user):
        raise PermissionDenied("You don't have access to this run.")

    if run.status not in (AITaskRun.Status.PENDING, AITaskRun.Status.RUNNING):
        return JsonResponse({"error": "This run has already finished."}, status=400)

    run.cancel_requested = True
    run.save(update_fields=["cancel_requested"])

    from .services import task_runner
    task_runner.cancel(run.id)

    return JsonResponse({"status": run.status, "cancel_requested": True})


@login_required
def ai_task_delete(request, run_id):
    """
    Deletes a finished AITaskRun and everything under it -
    AITaskRunDocument/AITaskResult both CASCADE off `run`, so this is a
    single row delete, not manual cleanup. AIRequestTrace.ai_task_run is
    SET_NULL, so the run's entry in AI Logs/Analytics survives the
    delete (matching AITaskResult.document's own "don't erase review
    history" SET_NULL rationale) - only the run and its results/document
    links disappear, not its trace/performance history.

    Same owner-or-admin authorization shape as ai_task_cancel, for the
    same reason (an admin clearing clutter from Admin > System Logs may
    not hold "pages.ai_tasks").

    A PENDING/RUNNING run must be cancelled first (400, not a silent
    no-op) rather than deleted out from under a background thread that
    might still be calling AITaskResult.objects.create(run=run, ...) -
    deleting the row mid-write would hit a foreign-key error instead of
    cleanly stopping anything.
    """

    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    run = get_object_or_404(AITaskRun, id=run_id)

    if run.user_id != request.user.id and not is_admin(request.user):
        raise PermissionDenied("You don't have access to this run.")

    if run.status in (AITaskRun.Status.PENDING, AITaskRun.Status.RUNNING):
        return JsonResponse({"error": "Cancel this run before deleting it."}, status=400)

    task_type_display = run.get_task_type_display()

    log_activity(
        actor=request.user,
        action="ai_task.deleted",
        description=f'{request.user.username} deleted an AI Task ({task_type_display})',
        request=request,
    )

    run.delete()

    return JsonResponse({"deleted": True})


@permission_required("pages.ai_tasks")
def ai_task_status(request, run_id):
    run = get_object_or_404(AITaskRun, id=run_id, user=request.user)

    return JsonResponse({
        "status": run.status,
        "cancel_requested": run.cancel_requested,
        "result_count": run.results.count(),
        "document_count": run.document_count,
        "error_message": run.error_message,
    })


@permission_required("pages.ai_tasks")
def ai_task_results(request, run_id):
    run = get_object_or_404(AITaskRun, id=run_id, user=request.user)

    per_document_results = list(run.results.filter(document__isnull=False).select_related("document"))
    corpus_results = list(run.results.filter(document__isnull=True))

    return render(
        request,
        "ai_tasks/wizard.html",
        {
            "task_types": AITaskRun.TaskType.choices,
            "ai_tasks_max_documents": settings.AI_TASKS_MAX_DOCUMENTS,
            "run": run,
            "per_document_results": per_document_results,
            "corpus_results": corpus_results,
            "result_count": len(per_document_results) + len(corpus_results),
            "breadcrumb_leaf": run.get_task_type_display(),
        },
    )


@permission_required("pages.ai_tasks")
def ai_task_history(request):
    runs = AITaskRun.objects.filter(user=request.user).order_by("-created_at")

    paginator = Paginator(runs, 15)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(request, "ai_tasks/history.html", {"page_obj": page_obj})


@permission_required("pages.ai_tasks")
def ai_task_export(request, run_id):
    run = get_object_or_404(AITaskRun, id=run_id, user=request.user)

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="ai_task_{run.id}_results.csv"'

    writer = csv.writer(response)
    writer.writerow(AI_TASK_RESULTS_HEADER)
    writer.writerows(get_ai_task_result_rows(run))

    return response


def health_check(request):
    """
    Public liveness/readiness probe (Sprint 10) for Docker/
    orchestrators - deliberately not @login_required (a health check
    has to work before anyone can log in) and deliberately minimal:
    see health_service.get_health_status() vs. settings_view's full
    system_status for the detailed, admin-only view.

    Always answers HTTP 200 - this is what a platform's *deploy* gate
    (Railway's healthcheckPath, or any orchestrator restart policy)
    should poll: "is the process up and able to answer HTTP", a
    liveness check, not "is every dependency currently perfect", a
    readiness check. The two used to be conflated (503 whenever
    get_health_status() computed anything other than "ok"), which
    means a transient DB/pgvector/LLM-provider blip - not the app
    itself being broken - could fail Railway's deploy healthcheck and
    trigger a restart loop, the same class of problem as the earlier
    slow-startup fix. The actual health verdict is unchanged and still
    fully present in the JSON body's "status" field
    (ok/degraded/critical) for anything that needs the nuanced signal -
    monitoring.html's auto-refresh already only reads `data.status`
    from the parsed body, never this response's HTTP status code, so
    that behavior is byte-for-byte unchanged by this.

    Excludes `recent_errors` from the JSON payload - it's a dict of raw
    RAG.models.ErrorGroup instances (health_service._recent_errors()),
    not JSON-serializable, and was never meant for this endpoint anyway:
    monitoring.html's auto-refresh only reads `data.status` from this
    response, and renders recent-errors panels straight from
    monitoring_view's own template context (a real get_health_status()
    call, not this JSON endpoint) where ErrorGroup attribute access
    works fine.
    """

    health = get_health_status(light=True)

    payload = {key: value for key, value in health.items() if key != "recent_errors"}

    return JsonResponse(payload, status=200)
