import time

from django.conf import settings

from ..models import QueryLog
from .citation_service import build_cited_context, extract_citations
from .context_compression_service import compress_context
from .llm_service import generate_answer
from .prompt_templates import is_not_found_answer
from .retrieval_service import retrieve_chunks


def calculate_confidence(retrieved_chunks, answer=None, citation_count=None):
    """
    Derive a 0-100 confidence score from the L2 distances of the
    retrieved chunks. Lower distance (closer match) means higher
    confidence. Both "vector" and "hyde" carry real embedding-space
    L2 distances (hyde just embeds an LLM-generated hypothetical
    passage instead of the raw question), so both count here.
    BM25/graph/multi_query matches (no comparable distance score)
    fall back to a neutral value.

    `answer` and `citation_count` are optional (Sprint 9) and fold in
    two hallucination-reduction signals on top of the retrieval-only
    score above:
    - If `answer` is the fixed "not found" fallback, confidence is 0
      regardless of how strong retrieval looked - there is no answer
      to be confident about.
    - If sources were retrieved but the answer cites none of them,
      that is weaker grounding evidence even when retrieval itself
      looked strong, so confidence is discounted (not zeroed - short
      factual answers can legitimately cite sparsely).

    Both default to None, so any existing caller that only passes
    `retrieved_chunks` keeps identical behavior.
    """

    if answer is not None and is_not_found_answer(answer):
        return 0

    distances = [
        chunk["score"]
        for chunk in retrieved_chunks
        if chunk.get("search_type") in ("vector", "hyde")
    ]

    if not distances:
        confidence = 40
    else:
        best_distance = min(distances)
        confidence = round((1 - min(best_distance, 1.0)) * 100)

    if citation_count == 0 and retrieved_chunks:
        confidence = round(confidence * 0.7)

    return max(0, min(confidence, 99))


SEARCH_TYPE_LABELS = (
    ("vector", "Vector"),
    ("bm25", "BM25"),
    ("graph", "Graph"),
    ("hyde", "HyDE"),
    ("multi_query", "Multi-query"),
)


def describe_search_method(retrieved_chunks):
    """
    Build a human-readable label for which retrieval sources actually
    contributed to this answer. Falls back to the original fixed
    label when nothing is retrieved, or when only vector/BM25
    contributed - unchanged from prior behavior either way.
    """

    types_present = {chunk.get("search_type") for chunk in retrieved_chunks}

    labels = [
        label
        for search_type, label in SEARCH_TYPE_LABELS
        if search_type in types_present
    ]

    if not labels:
        return "Hybrid (Vector + BM25)"

    return "Hybrid (" + " + ".join(labels) + ")"


def answer_question(question, user=None, filters=None):
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
        question,
        user=user,
        filters=filters,
    )

    # -------------------------
    # Compress Context
    # -------------------------
    # Removes chunks that are semantically redundant with one already
    # kept, before anything downstream (context, confidence, search
    # method label, QueryLog) sees them - so those all reflect exactly
    # what the LLM was given. Off by default; see settings.py.

    if settings.ENABLE_CONTEXT_COMPRESSION:
        retrieved_chunks = compress_context(retrieved_chunks)

    # -------------------------
    # Build Context (numbered for citations)
    # -------------------------

    context = build_cited_context(retrieved_chunks)

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

    # -------------------------
    # Extract Source Citations
    # -------------------------
    # Parses the "[n]" markers Gemini was prompted to include back
    # into the sources they reference (see citation_service.py); also
    # annotates matching entries in `retrieved_chunks` in place with
    # `citation_number`, for template display.

    citations = extract_citations(answer, retrieved_chunks)

    confidence = calculate_confidence(
        retrieved_chunks,
        answer=answer,
        citation_count=len(citations),
    )

    result = {

        "question": question,

        "answer": answer,

        "sources": retrieved_chunks,

        "citations": citations,

        "response_time_ms": response_time_ms,

        "confidence": confidence,

        "search_method": describe_search_method(retrieved_chunks),

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
