import time

from ..models import QueryLog
from .llm_service import generate_answer
from .retrieval_service import retrieve_chunks


def calculate_confidence(retrieved_chunks):
    """
    Derive a 0-100 confidence score from the
    vector search L2 distances of the retrieved
    chunks. Lower distance (closer match) means
    higher confidence. BM25-only matches (no
    "distance" score) fall back to a neutral value.
    """

    distances = [
        chunk["score"]
        for chunk in retrieved_chunks
        if chunk.get("search_type") == "vector"
    ]

    if not distances:
        return 40

    best_distance = min(distances)

    confidence = round((1 - min(best_distance, 1.0)) * 100)

    return max(0, min(confidence, 99))


def answer_question(question, user=None):
    """
    Answer the user's question using
    PostgreSQL + pgvector retrieval, and log
    the interaction for history/analytics.
    """

    start_time = time.perf_counter()

    # -------------------------
    # Retrieve Relevant Chunks
    # -------------------------

    retrieved_chunks = retrieve_chunks(
        question
    )

    # -------------------------
    # Build Context
    # -------------------------

    context = "\n\n".join(

        chunk["content"]

        for chunk in retrieved_chunks

    )

    # -------------------------
    # Generate LLM Answer
    # -------------------------

    answer = generate_answer(

        context,

        question

    )

    response_time_ms = round(
        (time.perf_counter() - start_time) * 1000
    )

    confidence = calculate_confidence(retrieved_chunks)

    result = {

        "question": question,

        "answer": answer,

        "sources": retrieved_chunks,

        "response_time_ms": response_time_ms,

        "confidence": confidence,

        "search_method": "Hybrid (Vector + BM25)",

    }

    # -------------------------
    # Persist Query Log
    # -------------------------

    if user is not None:

        QueryLog.objects.create(

            user=user,

            question=question,

            answer=answer,

            sources=retrieved_chunks,

            search_method=result["search_method"],

            response_time_ms=response_time_ms,

            confidence=confidence,

        )

    return result
