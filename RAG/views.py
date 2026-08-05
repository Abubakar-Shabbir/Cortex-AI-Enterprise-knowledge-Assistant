import csv

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

from .models import Document, DocumentChunk, Entity, QueryLog
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
from .services.upload_service import upload_document
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


            User.objects.create_user(

                username=username,

                email=email,

                password=password,

                first_name=first_name,

                last_name=last_name

            )


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


            return redirect('home')


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
def dashboard(request):
    """
    Admin-style workspace overview: KPI cards with trend sparklines,
    documents-over-time and document-type charts, and a recent
    documents table. Upload lives on the Documents page, questions
    live on the Ask AI page. system_status / activity_feed are already
    supplied globally by context_processors.sidebar_status.
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
    """

    upload_error = None

    if request.method == "POST" and "document" in request.FILES:

        title = request.POST.get("title")
        file = request.FILES.get("document")

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

        if doc.chunk_count == 0:
            status = "Processing"
        elif embedded >= doc.chunk_count:
            status = "Embedded"
        else:
            status = "Partial"

        documents_data.append({
            "doc": doc,
            "file_size": format_bytes(doc.file_size),
            "status": status,
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

        document.file.delete(save=False)
        document.delete()

        messages.success(request, "Document deleted.")

    return redirect("documents")


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


@login_required
def monitoring_view(request):
    """
    Admin-only system/infra monitoring - RAG pipeline configuration,
    database/pgvector status, and (Sprint 10) Redis/Celery health.
    Gated on request.user.is_staff, a real, already-existing Django
    field - no separate RBAC system was introduced for this. Replaces
    the old settings_view, which any authenticated user could reach;
    exposing DB/config internals to every user was never intentional,
    just never tightened until now.
    """

    if not request.user.is_staff:
        messages.error(request, "You don't have access to that page.")
        return redirect("home")

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
