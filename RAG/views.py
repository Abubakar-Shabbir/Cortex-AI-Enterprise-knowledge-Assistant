import django

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.core.paginator import Paginator
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect, render

from .models import Document, DocumentChunk, QueryLog
from .services.query_service import answer_question
from .services.stats_service import (
    get_analytics_data,
    get_dashboard_stats,
    get_recent_activity,
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
    Dashboard overview: quick stats and recent
    activity. Upload lives on the Documents page,
    questions live on the Ask AI page.
    """

    stats = get_dashboard_stats(request.user)
    activity = get_recent_activity(request.user)

    return render(
        request,
        "dashboard.html",
        {
            "stats": stats,
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

    if request.method == "POST" and "question" in request.POST:

        question = request.POST.get("question", "").strip()

        if question:
            result = answer_question(question, user=request.user)

    recent_questions = QueryLog.objects.filter(
        user=request.user
    ).order_by("-created_at")[:6]

    return render(
        request,
        "ask_ai.html",
        {
            "result": result,
            "recent_questions": recent_questions,
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

    return render(
        request,
        "documents.html",
        {
            "documents_data": documents_data,
            "upload_error": upload_error,
            "search_query": search_query,
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


NOT_FOUND_ANSWER = "couldn't find the answer"


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
            "answered": NOT_FOUND_ANSWER not in log.answer,
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
        },
    )


@login_required
def settings_view(request):

    system_status = get_system_status()

    return render(
        request,
        "settings.html",
        {
            "status": system_status,
            "chunk_size": settings.CHUNK_SIZE,
            "chunk_overlap": settings.CHUNK_OVERLAP,
            "top_k": settings.TOP_K,
            "django_version": django.get_version(),
        },
    )


# ==========================
# LOGOUT
# ==========================

def logout_user(request):


    logout(request)


    return redirect('login')
