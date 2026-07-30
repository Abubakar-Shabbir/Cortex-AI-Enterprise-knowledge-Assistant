from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.shortcuts import redirect, render

from .models import Document, DocumentChunk
from .services.query_service import answer_question
from .services.upload_service import upload_document
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
    Dashboard View

    Handles:
    1. Document Upload
    2. Question Answering
    3. Dashboard Display
    """

    # ==========================
    # POST REQUEST
    # ==========================

    if request.method == "POST":

        # ==========================
        # DOCUMENT UPLOAD
        # ==========================

        if "document" in request.FILES:

            title = request.POST.get("title")
            file = request.FILES.get("document")

            upload_document(
                user=request.user,
                title=title,
                file=file,
            )

            return redirect("home")

        # ==========================
        # QUESTION ANSWERING
        # ==========================

        elif "question" in request.POST:

            question = request.POST.get("question")

            result = answer_question(question)

            documents = Document.objects.filter(
                user=request.user
            )

            total_chunks = DocumentChunk.objects.filter(
                document__user=request.user
            ).count()

            return render(
                request,
                "dashboard.html",
                {
                    "documents": documents,
                    "total_chunks": total_chunks,
                    "question": result["question"],
                    "answer": result["answer"],
                    "sources": result["sources"],
                },
            )

    # ==========================
    # GET REQUEST
    # ==========================

    documents = Document.objects.filter(
        user=request.user
    )

    total_chunks = DocumentChunk.objects.filter(
        document__user=request.user
    ).count()

    return render(
        request,
        "dashboard.html",
        {
            "documents": documents,
            "total_chunks": total_chunks,
        },
    )

# ==========================
# LOGOUT
# ==========================

def logout_user(request):


    logout(request)


    return redirect('login')



