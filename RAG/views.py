from django.shortcuts import render, redirect
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from .services.retriever import retrieve_chunks
from .models import Document, DocumentChunk
from .services.retriever import retrieve_chunks
from .services.llm import generate_answer
from .services.query_service import search_vectors

from .services.document_processor import (
    extract_text,
    clean_text,
    create_chunks
)

from .services.embedding_service import generate_embedding
from .services.vector_store import save_vectors

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


    # ==========================
    # POST REQUEST
    # ==========================

    if request.method == "POST":


        # ==================================
        # 1. DOCUMENT UPLOAD
        # ==================================

        if "document" in request.FILES:


            title = request.POST.get("title")

            file = request.FILES.get("document")


            # Save document

            document = Document.objects.create(

                user=request.user,

                title=title,

                file=file

            )



            # Extract text

            text = extract_text(

                document.file.path

            )



            # Clean text

            text = clean_text(

                text

            )



            # Create chunks

            chunks = create_chunks(

                text

            )



            embeddings = []

            chunk_texts = []



            # Save chunks + embeddings

            for index, chunk in enumerate(chunks):


                DocumentChunk.objects.create(

                    document=document,

                    content=chunk,

                    chunk_number=index

                )


                embedding = generate_embedding(

                    chunk

                )


                embeddings.append(

                    embedding

                )


                chunk_texts.append(

                    chunk

                )



            # Save FAISS vectors

            save_vectors(

                embeddings,

                chunk_texts

            )



            print(
                "Vectors and chunks saved successfully"
            )


            return redirect("home")





        # ==================================
        # 2. ASK QUESTION
        # ==================================

        elif "question" in request.POST:


            question = request.POST.get(
                "question"
            )


            # Retrieve relevant chunks

            retrieved_chunks = retrieve_chunks(

                question

            )


            print("\nRetrieved Chunks\n")


            for chunk in retrieved_chunks:

                print(chunk)

                print("="*50)



            # Convert chunks into context

            context = "\n\n".join(

                retrieved_chunks

            )



            # Send context + question to LLM
            print("🔥 Gemini Request Sent")
            print(question)
            answer = generate_answer(

                question,

                context

            )



            print("\nAI ANSWER\n")

            print(answer)



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

                    "answer": answer

                }

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

            "total_chunks": total_chunks

        }

    )


# ==========================
# LOGOUT
# ==========================

def logout_user(request):


    logout(request)


    return redirect('login')



@login_required
def ask_question(request):

    if request.method == "POST":

        question = request.POST["question"]

        chunks = retrieve_chunks(
            question
        )

        context = "\n\n".join(chunks)

        answer = generate_answer(
            context,
            question
        )

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
                "answer": answer,
                "question": question
            }
        )

    return redirect("home")