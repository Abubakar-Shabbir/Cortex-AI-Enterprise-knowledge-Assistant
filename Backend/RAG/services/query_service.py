"""
Query Service (Ask AI)

answer_question() is the non-streaming, fully structured path (JSON-mode
answer: key_points/table, plus knowledge-graph-derived related_topics -
see llm_service.generate_answer() and
knowledge_service.get_related_topics_for_citations()).
answer_question_stream() is the streaming sibling: it keeps the plain-
text grounded prompt (build_answer_prompt(), not the JSON one) so tokens
can be typed live to the user - a partial JSON object can't be rendered
incrementally, and asking for structured extras would mean a second LLM
call per streamed question, which this codebase avoids on cost grounds
(the same reasoning Sprint 6's off-by-default flags document). A
streamed answer still gets related_topics (free, no LLM call) but
key_points=[]/table=None.

Both paths save one AIRequestTrace row each (RAG.services.observability_service
.save_trace()) - the same shared trace RAG.tasks.run_ai_task saves for
AI Tasks, so Ask AI and AI Tasks show up in the same AI Logs / Analytics
Performance views instead of each having their own.
"""

import logging
import time

from django.conf import settings

from ..models import AIRequestTrace, QueryLog
from .citation_service import build_cited_context, extract_citations
from .context_compression_service import compress_context
from .knowledge_service import get_related_topics_for_citations
from .llm_client import LLMProviderError, get_last_llm_meta, get_llm
from .llm_service import generate_answer
from .observability_service import save_trace
from .perf import timed_stage
from .prompt_templates import (
    NOT_FOUND_ANSWER,
    SERVICE_UNAVAILABLE_ANSWER,
    build_answer_prompt,
    is_not_found_answer,
    is_service_unavailable_answer,
)
from .retrieval_service import retrieve_chunks
from .trace import get_trace_id

logger = logging.getLogger(__name__)


def calculate_confidence(retrieved_chunks, answer=None, citation_count=None):
    """
    Derive a 0-100 confidence score from the L2 distances of the
    retrieved chunks. Lower distance (closer match) means higher
    confidence. Both "vector" and "hyde" carry real embedding-space
    L2 distances (hyde just embeds an LLM-generated hypothetical
    passage instead of the raw question), so both count here.
    BM25/graph/multi_query matches (no comparable distance score)
    fall back to a neutral value.

    `embedding_service.generate_embedding()` calls SentenceTransformer
    with `normalize_embeddings=True`, so every embedding is unit-length
    and the pgvector L2 distance `d` between two of them relates to
    their cosine similarity exactly: d**2 == 2 * (1 - cosine_similarity).
    Solving for cosine_similarity - not a flat `min(d, 1.0)` cap, which
    clamps to 0% confidence for any distance past 1.0 even though a
    distance a bit over 1.0 is a routine, still-fairly-close match (the
    real range for unit vectors is 0..2, where 2 is "exact opposite") -
    is what turns the raw distance into a bounded, meaningful score.

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

    if answer is not None and (is_not_found_answer(answer) or is_service_unavailable_answer(answer)):
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
        cosine_similarity = 1 - (best_distance ** 2) / 2
        confidence = round(max(0.0, min(1.0, cosine_similarity)) * 100)

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
    # Context Assembly
    # -------------------------
    # Compression removes chunks that are semantically redundant with
    # one already kept, before anything downstream (context,
    # confidence, search method label, QueryLog) sees them - so those
    # all reflect exactly what the LLM was given. Off by default; see
    # settings.py.

    with timed_stage("context assembly", chunks=len(retrieved_chunks), compression=settings.ENABLE_CONTEXT_COMPRESSION):

        if settings.ENABLE_CONTEXT_COMPRESSION:
            retrieved_chunks = compress_context(retrieved_chunks)

        context = build_cited_context(retrieved_chunks)

    # -------------------------
    # Generate LLM Answer
    # -------------------------

    with timed_stage("LLM request TOTAL", context_chars=len(context)):
        answer, extras = generate_answer(

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

    with timed_stage("citation validation", sources=len(retrieved_chunks)):
        citations = extract_citations(answer, retrieved_chunks)

    confidence = calculate_confidence(
        retrieved_chunks,
        answer=answer,
        citation_count=len(citations),
    )

    llm_meta = get_last_llm_meta() or {}

    result = {

        "question": question,

        "answer": answer,

        "sources": retrieved_chunks,

        "citations": citations,

        "response_time_ms": response_time_ms,

        "confidence": confidence,

        "search_method": describe_search_method(retrieved_chunks),

        # Which provider/model actually generated this answer - never
        # inferred from settings.LLM_PROVIDER, which is only what was
        # *requested*; this is what llm_client.py actually used,
        # including when settings.LLM_FALLBACK_ENABLED caused it to
        # differ from the configured primary. Empty when every
        # provider failed (SERVICE_UNAVAILABLE_ANSWER).
        "llm_provider": llm_meta.get("provider", ""),

        "llm_model": llm_meta.get("model", ""),

        "llm_fallback_used": llm_meta.get("fallback_used", False),

        "trace_id": get_trace_id(),

        "key_points": extras.get("key_points", []),

        "table": extras.get("table"),

        "related_topics": get_related_topics_for_citations(user, citations) if user is not None else [],

    }

    # -------------------------
    # Persist Query Log
    # -------------------------

    log = None

    if user is not None:

        log = QueryLog.objects.create(

            user=user,

            question=question,

            answer=answer,

            sources=retrieved_chunks,

            structured_data={"key_points": result["key_points"], "table": result["table"]},

            search_method=result["search_method"],

            response_time_ms=response_time_ms,

            confidence=confidence,

        )

    # -------------------------
    # Persist Execution Trace
    # -------------------------
    # A missing trace_id means no bind_trace_id() context is active
    # (e.g. a direct call from a management command/test) - nothing to
    # key a trace on, so this is skipped rather than saved under an
    # empty/colliding trace_id.

    trace_id = result["trace_id"]

    if trace_id:
        save_trace(
            trace_id,
            AIRequestTrace.Source.ASK_AI,
            user,
            query_log=log,
            status=(
                AIRequestTrace.Status.FAILED
                if is_service_unavailable_answer(answer)
                else AIRequestTrace.Status.COMPLETED
            ),
            total_duration_ms=response_time_ms,
            retrieved_chunks=len(retrieved_chunks),
            citation_count=len(citations),
        )

    return result


def answer_question_stream(question, user=None, filters=None):
    """
    Streaming counterpart to answer_question(), for RAG.views.ask_ai_stream.

    Retrieval and context assembly run exactly as they do above (both
    already fast - not worth streaming); only the LLM answer itself is
    yielded token-by-token as it's generated, via llm_client.generate_stream().

    Yields dicts:
    - {"type": "token", "text": str} for each piece of the answer as
      it streams in.
    - {"type": "done", "result": dict} exactly once, at the end - same
      shape answer_question() returns (question/answer/sources/
      citations/response_time_ms/confidence/search_method), built from
      the complete assembled answer, so citations/confidence/
      search_method/the persisted QueryLog are identical to what the
      non-streaming path would have produced for the same inputs.

    Mirrors llm_service.generate_answer()'s prompt-building and
    never-raise error handling (NOT_FOUND_ANSWER on an empty answer,
    SERVICE_UNAVAILABLE_ANSWER if every provider fails) rather than
    calling it directly, since generate_answer() itself is blocking,
    not a generator - this is the streaming sibling of that function,
    not a divergent reimplementation of it. LLMProviderError also
    covers a provider dying mid-stream (llm_client.generate_stream()'s
    contract: fallback is only possible before the first chunk of a
    given provider, so a failure after that propagates instead of
    silently switching providers mid-answer).
    """

    start_time = time.perf_counter()

    retrieved_chunks = retrieve_chunks(question, user=user, filters=filters)

    with timed_stage("context assembly", chunks=len(retrieved_chunks), compression=settings.ENABLE_CONTEXT_COMPRESSION):

        if settings.ENABLE_CONTEXT_COMPRESSION:
            retrieved_chunks = compress_context(retrieved_chunks)

        context = build_cited_context(retrieved_chunks)

    prompt = build_answer_prompt(context=context, question=question)

    answer_parts = []
    service_unavailable = False

    with timed_stage("LLM request TOTAL (streamed)", context_chars=len(context)):

        try:
            for piece in get_llm().generate_stream(
                prompt,
                temperature=settings.ANSWER_TEMPERATURE,
                max_tokens=settings.ANSWER_MAX_TOKENS,
            ):
                answer_parts.append(piece)
                yield {"type": "token", "text": piece}

        except LLMProviderError:
            logger.exception("Streaming LLM answer generation failed.")
            service_unavailable = True

    if service_unavailable:
        answer = SERVICE_UNAVAILABLE_ANSWER
    else:
        answer = "".join(answer_parts).strip() or NOT_FOUND_ANSWER

    response_time_ms = round(
        (time.perf_counter() - start_time) * 1000
    )

    with timed_stage("citation validation", sources=len(retrieved_chunks)):
        citations = extract_citations(answer, retrieved_chunks)

    confidence = calculate_confidence(
        retrieved_chunks,
        answer=answer,
        citation_count=len(citations),
    )

    llm_meta = get_last_llm_meta() or {}

    result = {

        "question": question,

        "answer": answer,

        "sources": retrieved_chunks,

        "citations": citations,

        "response_time_ms": response_time_ms,

        "confidence": confidence,

        "search_method": describe_search_method(retrieved_chunks),

        "llm_provider": llm_meta.get("provider", ""),

        "llm_model": llm_meta.get("model", ""),

        "llm_fallback_used": llm_meta.get("fallback_used", False),

        "trace_id": get_trace_id(),

        # A streamed answer keeps the plain-text prompt (see module
        # docstring) - no JSON extras to unpack, but related_topics is
        # still free (knowledge-graph lookup, no LLM call).
        "key_points": [],

        "table": None,

        "related_topics": get_related_topics_for_citations(user, citations) if user is not None else [],

    }

    log = None

    if user is not None:

        log = QueryLog.objects.create(

            user=user,

            question=question,

            answer=answer,

            sources=retrieved_chunks,

            structured_data={"key_points": result["key_points"], "table": result["table"]},

            search_method=result["search_method"],

            response_time_ms=response_time_ms,

            confidence=confidence,

        )

    trace_id = result["trace_id"]

    if trace_id:
        save_trace(
            trace_id,
            AIRequestTrace.Source.ASK_AI,
            user,
            query_log=log,
            status=AIRequestTrace.Status.FAILED if service_unavailable else AIRequestTrace.Status.COMPLETED,
            total_duration_ms=response_time_ms,
            retrieved_chunks=len(retrieved_chunks),
            citation_count=len(citations),
        )

    yield {"type": "done", "result": result}
