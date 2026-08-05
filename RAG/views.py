import csv
import os

import django

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify

from .decorators import admin_required, permission_required, super_admin_required
from .models import ActivityLog, Document, DocumentChunk, Entity, Permission, QueryLog, Role, UserRole
from .services.activity_log_service import log_activity
from .services.health_service import get_health_status
from .services.knowledge_service import (
    get_citation_explorer,
    get_entity_detail,
    get_graph_data,
    get_graph_insights,
    get_knowledge_overview,
    get_relation_types,
    get_relationships,
    search_entities,
)
from .services.prompt_templates import is_not_found_answer
from .services.query_service import answer_question
from .services.reports_service import (
    DOCUMENTS_REPORT_HEADER,
    USAGE_REPORT_HEADER,
    get_documents_report_rows,
    get_usage_report_rows,
)
from .services.permission_service import (
    SUPER_ADMIN,
    USER,
    get_dashboard_url_for_user,
    is_super_admin,
    user_has_permission,
)
from .services.retrieval_filters import RetrievalFilters
from .services.stats_service import (
    get_analytics_data,
    get_dashboard_stats,
    get_document_type_breakdown,
    get_documents_over_time,
    get_kpi_trends,
    get_recent_activity,
    get_recent_documents_table,
    get_system_status,
)
from .services.system_config_service import get_config, save_config
from .services.upload_service import process_uploaded_document, upload_document
from .utils.formatting import format_bytes


def signup(request):

    if request.method == "POST":

        fullname = request.POST['fullname']
        email = request.POST['email']
        username = request.POST['username']
        password = request.POST['password']
        confirm_password = request.POST['confirm_password']


        if password == confirm_password:

            name_parts = fullname.split()

            first_name = name_parts[0]

            last_name = " ".join(
                name_parts[1:]
            )


            new_user = User.objects.create_user(

                username=username,

                email=email,

                password=password,

                first_name=first_name,

                last_name=last_name

            )

            default_role, _ = Role.objects.get_or_create(
                slug=USER,
                defaults={"name": "User", "is_system": True},
            )

            UserRole.objects.create(user=new_user, role=default_role)

            return redirect('login')


    return render(
        request,
        'signup.html'
    )

def login_user(request):

    if request.method == "POST":


        username = request.POST['username']

        password = request.POST['password']


        user = authenticate(

            request,

            username=username,

            password=password

        )


        if user is not None:


            login(
                request,
                user
            )

            log_activity(
                actor=user,
                action="user.login",
                description=f"{user.username} logged in",
            )

            return redirect(get_dashboard_url_for_user(user))


        else:

            return render(

                request,

                'login.html',

                {
                    "error":
                    "Invalid Username or Password"
                }

            )


    return render(
        request,
        'login.html'
    )



@login_required
def home_redirect(request):
    """
    '/' - sends every logged-in user to the dashboard for their role
    (Admin/Super Admin -> /admin/, User -> /dashboard/). Existing
    templates keep linking to {% url 'home' %} as a stable "take me to
    my dashboard" entry point regardless of role.
    """

    return redirect(get_dashboard_url_for_user(request.user))


@login_required
def user_dashboard(request):
    """
    User Dashboard (/dashboard/) - a deliberately simpler overview than
    the Admin Dashboard: four stat cards, recent documents, recent
    questions, and quick actions. No charts, no cross-user data, no
    admin-only widgets - see templates/user_dashboard.html and
    templates/user/_sidebar.html, both distinct from the admin
    equivalents.
    """

    stats = get_dashboard_stats(request.user)
    activity = get_recent_activity(request.user)

    return render(
        request,
        "user_dashboard.html",
        {
            "stats": stats,
            **activity,
        },
    )


@admin_required
def admin_dashboard_view(request):
    """
    Admin Dashboard (/admin/) - KPI cards with trend sparklines,
    documents-over-time and document-type charts, and a recent
    documents table. system_status / activity_feed are already
    supplied globally by context_processors.sidebar_status. Left
    exactly as designed - not touched by the RBAC/User Dashboard work.
    """

    stats = get_dashboard_stats(request.user)
    activity = get_recent_activity(request.user)
    trends = get_analytics_data(request.user, days=7)

    return render(
        request,
        "dashboard.html",
        {
            "stats": stats,
            "trends": trends,
            "kpi_trends": get_kpi_trends(request.user),
            "documents_over_time": get_documents_over_time(request.user, days=7),
            "document_types": get_document_type_breakdown(request.user),
            "recent_documents_table": get_recent_documents_table(request.user),
            **activity,
        },
    )


@login_required
def ask_ai(request):
    """
    Dedicated Ask AI page: submit a question,
    show the answer, sources, confidence,
    response time and search method used.
    """

    result = None

    selected_document_id = request.POST.get("document_id", "")

    if request.method == "POST" and "question" in request.POST:

        question = request.POST.get("question", "").strip()

        if question:

            filters = RetrievalFilters.from_request(
                document_id=selected_document_id
            )

            result = answer_question(
                question,
                user=request.user,
                filters=filters,
            )

    recent_questions = QueryLog.objects.filter(
        user=request.user
    ).order_by("-created_at")[:6]

    documents = Document.objects.filter(
        user=request.user
    ).order_by("title")

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
            "selected_document_id": selected_document_id,
            "suggested_questions": suggested_questions,
        },
    )


@login_required
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

            upload_document(
                user=request.user,
                title=title,
                file=file,
            )

            return redirect("documents")

        except ValueError as e:

            upload_error = str(e)

    search_query = request.GET.get("q", "").strip()

    documents = (
        Document.objects.filter(user=request.user)
        .annotate(embedded_chunks=Count("chunks__vector"))
        .order_by("-uploaded_at")
    )

    if search_query:
        documents = documents.filter(title__icontains=search_query)

    documents_data = []

    for doc in documents:

        embedded = doc.embedded_chunks

        if doc.processing_status == Document.ProcessingStatus.PENDING:
            status = "Pending"
            percent = 0
        elif doc.processing_status == Document.ProcessingStatus.FAILED:
            status = "Failed"
            percent = 0
        elif doc.processing_status == Document.ProcessingStatus.PROCESSING:
            status = "Processing"
            percent = round((embedded / doc.chunk_count) * 100) if doc.chunk_count else 0
        elif doc.chunk_count and embedded >= doc.chunk_count:
            status = "Embedded"
            percent = 100
        else:
            # processing_status is COMPLETED but embedded < chunk_count is
            # unexpected (e.g. a vector insert failed silently) - surfaced
            # honestly as Partial rather than claiming Embedded.
            status = "Partial"
            percent = round((embedded / doc.chunk_count) * 100) if doc.chunk_count else 0

        documents_data.append({
            "doc": doc,
            "file_size": format_bytes(doc.file_size),
            "status": status,
            "percent": percent,
        })

    embedded_count = sum(1 for item in documents_data if item["status"] == "Embedded")
    total_storage = sum(item["doc"].file_size for item in documents_data)

    return render(
        request,
        "documents.html",
        {
            "documents_data": documents_data,
            "upload_error": upload_error,
            "search_query": search_query,
            "total_documents": len(documents_data),
            "embedded_count": embedded_count,
            "total_storage": format_bytes(total_storage),
        },
    )


@login_required
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
        )

        messages.success(request, "Document deleted.")

    return redirect("documents")


@login_required
def document_embed(request, doc_id):
    """
    Triggers processing (extract/chunk/embed/graph-enrich) for one
    PENDING or previously-FAILED document - the explicit, per-document
    counterpart to what upload_document() used to run automatically at
    upload time. Dispatches to a Celery worker when
    settings.ENABLE_ASYNC_PROCESSING is on, so this request returns
    immediately and documents.html's per-row progress bar polls
    document_status below; otherwise runs inline and blocks only this
    one request until done (same as the pre-Sprint-10 default).
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

        from .tasks import process_document_task

        process_document_task.delay(document.id)

        messages.success(request, f'"{document.title}" is processing in the background.')

    else:

        try:
            process_uploaded_document(document)
            messages.success(request, f'"{document.title}" processed.')
        except Exception:
            messages.error(request, f'Processing "{document.title}" failed - check the server logs.')

    return redirect("documents")


@login_required
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


@login_required
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


@login_required
def analytics_view(request):

    data = get_analytics_data(request.user)

    return render(
        request,
        "analytics.html",
        {
            "data": data,
        },
    )


@login_required
def profile_view(request):

    password_form = PasswordChangeForm(request.user)

    if request.method == "POST":

        if request.POST.get("form") == "profile":

            user = request.user

            user.first_name = request.POST.get("first_name", "").strip()
            user.last_name = request.POST.get("last_name", "").strip()
            user.email = request.POST.get("email", "").strip()
            user.save()

            messages.success(request, "Profile updated.")

            return redirect("profile")

        elif request.POST.get("form") == "password":

            password_form = PasswordChangeForm(request.user, request.POST)

            if password_form.is_valid():

                user = password_form.save()

                update_session_auth_hash(request, user)

                messages.success(request, "Password updated.")

                return redirect("profile")

            else:

                messages.error(request, "Please correct the errors below.")

    return render(
        request,
        "profile.html",
        {
            "password_form": password_form,
            "current_user_agent": request.META.get("HTTP_USER_AGENT", "Unknown device"),
        },
    )


@permission_required("system.view_health")
def monitoring_view(request):
    """
    Admin-only system/infra monitoring - RAG pipeline configuration,
    database/pgvector status, and (Sprint 10) Redis/Celery health.
    Gated by the "system.view_health" RBAC permission (see
    RAG/decorators.py, RAG/services/permission_service.py) rather than
    request.user.is_staff - a role's permission set can now be changed
    without touching this view.
    """

    system_status = get_system_status()
    health = get_health_status()

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
            "settings_use_redis_cache": settings.USE_REDIS_CACHE,
        },
    )


@permission_required("users.view_all")
def admin_users_view(request):
    """
    Admin > Users - list every user with their assigned role and
    status, and handle suspend/activate/delete/assign-role actions.
    Metadata-only, per the RBAC scope decision: this never exposes
    another user's document content or Q&A answers, only account-level
    info (username, email, role, active status, join date).
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

        elif action == "suspend":
            target_user.is_active = False
            target_user.save(update_fields=["is_active"])
            log_activity(
                actor=request.user,
                action="user.suspended",
                description=f'"{target_user.username}" suspended by {request.user.username}',
            )
            messages.success(request, f'"{target_user.username}" suspended.')

        elif action == "activate":
            target_user.is_active = True
            target_user.save(update_fields=["is_active"])
            log_activity(
                actor=request.user,
                action="user.reactivated",
                description=f'"{target_user.username}" reactivated by {request.user.username}',
            )
            messages.success(request, f'"{target_user.username}" reactivated.')

        elif action == "delete":
            if target_user == request.user:
                messages.error(request, "You can't delete your own account.")
            else:
                deleted_username = target_user.username
                target_user.delete()
                log_activity(
                    actor=request.user,
                    action="user.deleted",
                    description=f'"{deleted_username}" deleted by {request.user.username}',
                )
                messages.success(request, "User deleted.")

        elif action == "assign_role":

            role_slug = request.POST.get("role")

            if role_slug == SUPER_ADMIN and not is_super_admin(request.user):
                messages.error(request, "Only a Super Admin can grant the Super Admin role.")
            else:
                role = get_object_or_404(Role, slug=role_slug)
                UserRole.objects.update_or_create(
                    user=target_user,
                    defaults={"role": role, "assigned_by": request.user},
                )
                log_activity(
                    actor=request.user,
                    action="user.role_changed",
                    description=f'"{target_user.username}" set to {role.name} by {request.user.username}',
                )
                messages.success(request, f'"{target_user.username}" is now {role.name}.')

        return redirect("admin_users")

    users_list = (
        User.objects.select_related("role_assignment__role")
        .order_by("-date_joined")
    )

    return render(
        request,
        "admin/users.html",
        {
            "users_list": users_list,
            "roles": Role.objects.all().order_by("name"),
        },
    )


@super_admin_required
def admin_roles_view(request):
    """
    Admin > Roles - define what each Role can do (create a role, set
    which Permissions it grants). More sensitive than assigning an
    existing role to a user (admin_users_view, gated by the
    "users.assign_role" permission any admin can be granted): this
    changes what a role itself means for everyone who holds it, so
    it's restricted to Super Admin. This is what makes "future roles
    added without touching code" concretely true - creating a Manager/
    HR/Auditor role and choosing its permissions happens entirely here.
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
                )
                messages.success(request, f'Role "{name}" created.')

        elif action == "update_permissions":

            role = get_object_or_404(Role, id=request.POST.get("role_id"))
            selected_codenames = request.POST.getlist("permissions")
            role.permissions.set(Permission.objects.filter(codename__in=selected_codenames))
            log_activity(
                actor=request.user,
                action="role.permissions_updated",
                description=f'Permissions updated for "{role.name}" by {request.user.username}',
            )
            messages.success(request, f'Permissions updated for "{role.name}".')

        elif action == "delete_role":

            role = get_object_or_404(Role, id=request.POST.get("role_id"))

            if role.is_system:
                messages.error(request, f'"{role.name}" is a built-in role and can\'t be deleted.')
            elif role.user_assignments.exists():
                messages.error(
                    request,
                    f'"{role.name}" is still assigned to {role.user_assignments.count()} user(s) - reassign them first.',
                )
            else:
                role_name = role.name
                role.delete()
                log_activity(
                    actor=request.user,
                    action="role.deleted",
                    description=f'Role "{role_name}" deleted by {request.user.username}',
                )
                messages.success(request, f'Role "{role_name}" deleted.')

        return redirect("admin_roles")

    return render(
        request,
        "admin/roles.html",
        {
            "roles": Role.objects.prefetch_related("permissions").order_by("name"),
            "permissions": Permission.objects.all().order_by("codename"),
        },
    )


@permission_required("settings.manage_llm")
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

    Note: every field on this one form is currently gated by a single
    permission ("settings.manage_llm"); a future role holding, say,
    only "settings.manage_chunking" would need this view split into
    per-section forms to be enforced field-by-field - not done here.
    """

    config = get_config()

    if request.method == "POST":

        try:
            data = {
                "llm_provider": request.POST.get("llm_provider", config.llm_provider),
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

        save_config(data, request.user)

        log_activity(
            actor=request.user,
            action="settings.updated",
            description=f"RAG pipeline configuration updated by {request.user.username}",
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
        },
    )


@permission_required("queries.view_all_logs")
def admin_queries_view(request):
    """
    Admin > Queries - a workspace-wide view of every user's Ask AI
    query log. Metadata only, per the RBAC scope decision: question
    text, owner, confidence, response time, search method, and
    timestamp are shown (comparable to a document's title/metadata) -
    the generated answer text itself is never displayed here, since
    that crosses into another user's actual Q&A content.
    """

    logs = QueryLog.objects.select_related("user").order_by("-created_at")

    paginator = Paginator(logs, 20)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "admin/queries.html",
        {"page_obj": page_obj},
    )


@permission_required("activity.view_all_logs")
def admin_activity_logs_view(request):
    """
    Admin > Activity Logs - a workspace-wide activity feed, merging
    two real sources the same way context_processors.sidebar_status()
    already merges them for the per-user notification dropdown, just
    workspace-wide instead of one user's latest 3:

    - Document uploads (Document.uploaded_at) - not written to
      ActivityLog, since it's already a real timestamped event on an
      existing model; duplicating it into a second table would just
      be two sources of truth for the same fact.
    - Everything ActivityLog actually covers (deletions, suspensions,
      role changes, logins) - see RAG.services.activity_log_service.

    Each source is capped before merging/sorting since this combines
    two tables in Python rather than a DB-level UNION - unbounded here
    would mean pulling entire tables just to paginate a handful of
    rows.
    """

    events = []

    for doc in Document.objects.select_related("user").order_by("-uploaded_at")[:300]:
        events.append({
            "icon": "file-up",
            "actor": doc.user.username,
            "text": f'"{doc.title}" uploaded',
            "at": doc.uploaded_at,
        })

    activity_icons = {
        "document.deleted": "trash-2",
        "user.suspended": "user-x",
        "user.reactivated": "user-check",
        "user.deleted": "user-minus",
        "user.role_changed": "shield",
        "user.login": "log-in",
    }

    for log in ActivityLog.objects.select_related("actor").order_by("-created_at")[:300]:
        events.append({
            "icon": activity_icons.get(log.action, "activity"),
            "actor": log.actor.username if log.actor else "system",
            "text": log.description,
            "at": log.created_at,
        })

    events.sort(key=lambda event: event["at"], reverse=True)

    paginator = Paginator(events, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "admin/activity_logs.html",
        {"page_obj": page_obj},
    )


@login_required
def knowledge_base_view(request):
    """
    Browse Knowledge: overview stats, category breakdown, and a
    filterable/searchable entity list. The Knowledge Base's other
    pages (Entity/Relationship Explorer, Graph, Citations) are reached
    from the tabs on this page rather than the sidebar, keeping the
    main nav to one entry per section.
    """

    overview = get_knowledge_overview(request.user)

    query = request.GET.get("q", "").strip()
    entity_type = request.GET.get("type", "").strip()

    entities_page = search_entities(
        request.user, query=query, entity_type=entity_type, page=request.GET.get("page")
    )

    return render(
        request,
        "knowledge/browse.html",
        {
            "overview": overview,
            "entities_page": entities_page,
            "query": query,
            "selected_type": entity_type,
        },
    )


@login_required
def entity_detail_view(request, entity_id):

    detail = get_entity_detail(request.user, entity_id)

    if detail is None:
        messages.error(request, "That entity couldn't be found.")
        return redirect("knowledge_base")

    return render(
        request,
        "knowledge/entity_detail.html",
        {
            **detail,
            "breadcrumb_leaf": detail["entity"].display_name,
        },
    )


@login_required
def relationships_view(request):

    relation_type = request.GET.get("type", "").strip()

    relationships_page = get_relationships(
        request.user, relation_type=relation_type, page=request.GET.get("page")
    )

    return render(
        request,
        "knowledge/relationships.html",
        {
            "relationships_page": relationships_page,
            "relation_types": get_relation_types(request.user),
            "selected_type": relation_type,
        },
    )


@login_required
def knowledge_graph_view(request):

    graph_data = get_graph_data(request.user)
    insights = get_graph_insights(request.user)

    return render(
        request,
        "knowledge/graph.html",
        {
            "graph_data": graph_data,
            "insights": insights,
        },
    )


@login_required
def citation_explorer_view(request):

    citations = get_citation_explorer(request.user)

    return render(
        request,
        "knowledge/citations.html",
        {
            "citations": citations,
        },
    )


@login_required
def reports_view(request):
    return render(request, "reports.html")


@login_required
def export_documents_report(request):

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="documents_report.csv"'

    writer = csv.writer(response)
    writer.writerow(DOCUMENTS_REPORT_HEADER)
    writer.writerows(get_documents_report_rows(request.user))

    return response


@login_required
def export_usage_report(request):

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="usage_report.csv"'

    writer = csv.writer(response)
    writer.writerow(USAGE_REPORT_HEADER)
    writer.writerows(get_usage_report_rows(request.user))

    return response


def health_check(request):
    """
    Public liveness/readiness probe (Sprint 10) for Docker/
    orchestrators - deliberately not @login_required (a health check
    has to work before anyone can log in) and deliberately minimal:
    see health_service.get_health_status() vs. settings_view's full
    system_status for the detailed, admin-only view.
    """

    health = get_health_status()

    status_code = 200 if health["status"] == "ok" else 503

    return JsonResponse(health, status=status_code)


# ==========================
# LOGOUT
# ==========================

def logout_user(request):


    logout(request)


    return redirect('login')
