import contextvars
import hashlib
import logging
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.core.cache import cache
from pgvector.django import L2Distance

from ..models import ChunkEmbedding
from .document_access_service import get_accessible_document_ids
from .embedding_service import generate_embedding
from .bm25_service import bm25_search
from .dynamic_topk_service import compute_dynamic_top_k
from .graph_retrieval_service import graph_search
from .hyde_service import generate_hypothetical_document
from .perf import Timer, timed_stage
from .query_expansion_service import expand_query
from .reranker_service import rerank_chunks
from .retrieval_filters import apply_document_filters

logger = logging.getLogger(__name__)


def _vector_similarity_search(embedding, top_k, search_type="vector", filters=None, user=None, accessible_document_ids=None):
    """
    Shared pgvector L2Distance nearest-neighbor lookup. Both
    vector_search() (embeds the question) and hyde_search() (embeds a
    generated hypothetical passage) are the same query over
    ChunkEmbedding once you already have an embedding vector - this is
    the one place that runs it, tagged with whichever `search_type`
    the caller is using it for.

    `user` is required for a non-empty result: like
    graph_retrieval_service.graph_search(), a missing `user` fails
    closed (returns []) rather than searching every user's chunks -
    this table has no other tenant isolation, so an omitted `user`
    must never silently mean "everyone". Scoped to `user`'s full
    accessible set (owned + Organization Library + shared-with-them),
    not just documents they own - see document_access_service.

    `accessible_document_ids`, when provided, is used as-is instead of
    recomputing it here - lets retrieve_chunks() compute it once and
    share it across vector/BM25/graph search rather than each source
    independently re-running the same accessible-scope query.

    Never raises, matching graph_search()/hyde_search()'s "a failed
    source degrades to no contribution" contract - previously this had
    no try/except at all, unlike every other retrieval source, so a DB
    hiccup here propagated uncaught through retrieve_chunks()'s thread
    pool and answer_question() into a raw 500 for the whole request.
    """

    if user is None:
        return []

    try:
        accessible_ids = (
            accessible_document_ids if accessible_document_ids is not None else get_accessible_document_ids(user)
        )

        if not accessible_ids:
            return []

        # select_related avoids an N+1: without it, every result row below
        # triggers 2 extra queries the moment the loop touches
        # item.chunk.content / item.chunk.document.title (live-profiled:
        # 13 queries for a 5-result search instead of the 3 this produces).
        queryset = ChunkEmbedding.objects.filter(chunk__document_id__in=accessible_ids).select_related(
            "chunk", "chunk__document"
        ).annotate(
            distance=L2Distance("embedding", embedding)
        )

        queryset = apply_document_filters(
            queryset, filters, document_field="chunk__document"
        )

        similar_chunks = queryset.order_by("distance")[:top_k]

        results = []

        for item in similar_chunks:

            results.append(

                {

                    "content": item.chunk.content,

                    "document": item.chunk.document.title,

                    "chunk_number": item.chunk.chunk_number,

                    "score": round(item.distance, 4),

                    "search_type": search_type,

                }

            )

        return results

    except Exception:
        logger.exception("Vector similarity search failed (search_type=%s)", search_type)
        return []


def vector_search(question, top_k=None, filters=None, user=None, accessible_document_ids=None):
    """
    Semantic Vector Search

    Never raises: generate_embedding() failure (e.g. the embedding
    model unavailable) degrades to no vector contribution rather than
    failing the whole hybrid retrieval call.
    """

    try:
        query_embedding = generate_embedding(question)
    except Exception:
        logger.exception("Query embedding failed in vector_search")
        return []

    return _vector_similarity_search(
        query_embedding,
        top_k or settings.TOP_K,
        search_type="vector",
        filters=filters,
        user=user,
        accessible_document_ids=accessible_document_ids,
    )


def hyde_search(question, top_k=None, filters=None, user=None, accessible_document_ids=None):
    """
    HyDE Retrieval (Hypothetical Document Embeddings)

    Embeds an LLM-generated hypothetical answer passage instead of the
    raw question, then runs the same nearest-neighbor lookup as
    vector_search(). Falls back to [] if the LLM call fails or is
    unavailable - callers should treat that as "no HyDE contribution
    this time", not an error.
    """

    hypothetical_document = generate_hypothetical_document(question)

    if not hypothetical_document:
        return []

    try:
        hypothetical_embedding = generate_embedding(hypothetical_document)
    except Exception:
        logger.exception("Query embedding failed in hyde_search")
        return []

    return _vector_similarity_search(
        hypothetical_embedding,
        top_k or settings.TOP_K,
        search_type="hyde",
        filters=filters,
        user=user,
        accessible_document_ids=accessible_document_ids,
    )


def _run_timed(label, fn, *args, **kwargs):
    """
    Runs `fn` on whichever thread calls this (a ThreadPoolExecutor
    worker, when used from retrieve_chunks() below), logging its own
    timing from inside that thread - accurate regardless of which
    order the main thread later collects each Future's .result() in,
    unlike timing measured from the collection side.

    Always closes this thread's DB connection before returning: Django
    only auto-closes a request's DB connection via the normal request/
    response cycle signal handlers, which never fire for an ad-hoc
    ThreadPoolExecutor thread - skipping this would leak one
    connection per retrieval call, accumulating over the app's
    lifetime.
    """

    from django.db import connection

    try:
        with timed_stage(label):
            return fn(*args, **kwargs)
    finally:
        connection.close()


def _submit_timed(executor, label, fn, *args, **kwargs):
    """
    executor.submit(_run_timed, ...), but running inside a copy of the
    calling thread's contextvars context - a plain executor.submit()
    does NOT propagate contextvars into the worker thread (that's an
    asyncio-Task behavior, not a ThreadPoolExecutor one), so without
    this, every timed_stage() call made from inside a worker thread
    (vector/BM25/graph/HyDE/multi-query below) would see no bound
    trace_id/stage list and silently vanish from the request's trace -
    confirmed live: those stages logged "[-]" instead of the real trace
    id before this fix. contextvars.Context.run() executes `fn` with
    that captured context installed on the worker thread, so
    RAG.services.trace.get_trace_id()/record_stage() (and hence
    TraceIdLogFilter, and the AIRequestTrace stage list) work correctly
    for concurrently-run stages too, not just ones on the main thread.
    """

    ctx = contextvars.copy_context()

    return executor.submit(ctx.run, _run_timed, label, fn, *args, **kwargs)


def _retrieval_cache_key(question, user, filters, effective_top_k):
    """
    Cache key for a full retrieve_chunks() result - identical (question,
    user, filters, top_k) reuses it rather than recomputing embed+BM25+
    graph from scratch.

    Also fingerprints every settings flag retrieve_chunks() actually
    branches on below (query expansion/HyDE/multi-query/reranker, plus
    the two knobs that change what those produce even when still on:
    MULTI_QUERY_VARIANTS, RERANKER_CANDIDATE_MULTIPLIER). These are
    live-editable per-process via system_config_service.py
    (apply_config_to_settings() monkey-patches settings.* directly, so
    `settings.ENABLE_RERANKER` here already reflects the latest saved
    value) - without them in the key, an Admin toggling e.g. ENABLE_RERANKER
    had no visible effect on a repeated question until the previous
    (pre-toggle) cached entry aged out past settings.RETRIEVAL_CACHE_TTL.
    """

    flag_fingerprint = (
        f"{settings.ENABLE_QUERY_EXPANSION}"
        f"|{settings.ENABLE_HYDE}"
        f"|{settings.ENABLE_MULTI_QUERY}:{settings.MULTI_QUERY_VARIANTS}"
        f"|{settings.ENABLE_RERANKER}:{settings.RERANKER_CANDIDATE_MULTIPLIER}"
    )
    raw = f"{question}|{user.id if user else 'anon'}|{filters!r}|{effective_top_k}|{flag_fingerprint}"

    return "retrieve_chunks:" + hashlib.sha256(raw.encode()).hexdigest()


def retrieve_chunks(question, user=None, filters=None, top_k=None):
    """
    Hybrid Retrieval
    Vector Search + BM25 + Knowledge Graph, optionally enriched with
    HyDE and Multi-query retrieval (Sprint 6 - both off by default,
    see settings.ENABLE_HYDE / settings.ENABLE_MULTI_QUERY), and
    optionally re-scored by a BGE cross-encoder reranker (Sprint 7 -
    off by default, see settings.ENABLE_RERANKER).

    `user` and `filters` are optional and default to None/no-filter,
    so any existing caller keeps identical behavior. `top_k` lets a
    caller override retrieval depth directly; when omitted it's
    settings.ENABLE_DYNAMIC_TOP_K-dependent (dynamic heuristic or the
    fixed settings.TOP_K).

    Every independent source (vector/BM25/graph, plus HyDE/multi-query
    when enabled) runs concurrently rather than one after another -
    they share no data dependency, only the final merge does. The
    whole result is also cached for settings.RETRIEVAL_CACHE_TTL
    seconds per (question, user, filters, top_k) - a repeated question
    skips retrieval entirely on a cache hit. The LLM answer is never
    cached here (see query_service.answer_question()) - only
    retrieval, so answer freshness/quality is unaffected either way.
    """

    overall_timer = Timer()

    effective_top_k = top_k or (
        compute_dynamic_top_k(question)
        if settings.ENABLE_DYNAMIC_TOP_K
        else settings.TOP_K
    )

    cache_key = _retrieval_cache_key(question, user, filters, effective_top_k)
    cached = cache.get(cache_key)

    if cached is not None:
        logger.info("[PERF] retrieve_chunks TOTAL %8.1fms cache=hit results=%d", overall_timer.stop(), len(cached))
        return cached

    # Computed once and shared across vector/BM25/graph/HyDE/multi-query
    # below instead of each source independently re-running the same
    # "which documents can this user see" query - previously 3+ identical
    # queries per question (more with HyDE/multi-query enabled).
    accessible_document_ids = get_accessible_document_ids(user) if user is not None else None

    # When reranking is enabled, over-fetch a larger candidate pool
    # from each source so the reranker has real alternatives to
    # reorder, rather than just re-scoring an already-truncated list.
    retrieval_top_k = (
        effective_top_k * settings.RERANKER_CANDIDATE_MULTIPLIER
        if settings.ENABLE_RERANKER
        else effective_top_k
    )

    # Query Expansion enriches only the BM25 (lexical) query - see
    # query_expansion_service for why vector search keeps the raw
    # question. expand_query() never raises and falls back to
    # `question` unchanged, so this is safe even when the flag is off
    # or the LLM call fails.
    #
    # Query Expansion only gates BM25's input, not vector/graph/HyDE -
    # so rather than blocking the whole function on it before the
    # parallel fan-out below (as a naive read of "BM25 needs
    # lexical_query first" would suggest), it's submitted to the SAME
    # pool as everything else, and BM25's own thread waits on its
    # Future internally. When both Query Expansion and HyDE are
    # enabled (each a real LLM call), this is the difference between
    # ~13s (6.5s expansion, blocking, then 6.5s more for HyDE) and
    # ~6.5s (both running at once, total bounded by whichever is
    # slower) - live-profiled on this exact question.
    with ThreadPoolExecutor(max_workers=6) as executor:

        expansion_future = None
        if settings.ENABLE_QUERY_EXPANSION:
            expansion_future = _submit_timed(executor, "query expansion", expand_query, question)

        def _bm25_after_expansion():
            lexical_query = expansion_future.result() if expansion_future is not None else question
            return bm25_search(
                lexical_query, retrieval_top_k, filters=filters, user=user,
                accessible_document_ids=accessible_document_ids,
            )

        # Every submit below preserves each function's own original
        # positional-vs-keyword calling convention exactly (not just
        # matching values by position) - some existing tests assert on
        # Mock.call_args.kwargs specifically, and this also just keeps
        # each call site consistent with that function's own signature
        # elsewhere in the codebase.
        vector_future = _submit_timed(
            executor, "vector search", vector_search, question, top_k=retrieval_top_k, filters=filters, user=user,
            accessible_document_ids=accessible_document_ids,
        )
        bm25_future = _submit_timed(executor, "hybrid search (BM25)", _bm25_after_expansion)
        graph_future = _submit_timed(
            executor, "knowledge graph retrieval", graph_search, question, user, retrieval_top_k, filters=filters,
            accessible_document_ids=accessible_document_ids,
        )

        hyde_future = None
        if settings.ENABLE_HYDE:
            hyde_future = _submit_timed(
                executor, "HyDE retrieval", hyde_search, question, top_k=retrieval_top_k, filters=filters, user=user,
                accessible_document_ids=accessible_document_ids,
            )

        multi_query_future = None
        if settings.ENABLE_MULTI_QUERY:
            # Imported here, not at module level, to avoid a circular
            # import: multi_query_service reuses this module's
            # vector_search() and bm25_service.bm25_search() directly
            # rather than duplicating retrieval logic.
            from .multi_query_service import multi_query_search

            multi_query_future = _submit_timed(
                executor, "multi-query retrieval", multi_query_search,
                question, top_k=retrieval_top_k, filters=filters, user=user,
                accessible_document_ids=accessible_document_ids,
            )

        vector_results = vector_future.result()
        bm25_results = bm25_future.result()
        graph_results = graph_future.result()
        hyde_results = hyde_future.result() if hyde_future is not None else []
        multi_query_results = multi_query_future.result() if multi_query_future is not None else []

    all_results = (
        vector_results
        + bm25_results
        + graph_results
        + hyde_results
        + multi_query_results
    )

    merged = {}

    for item in all_results:

        key = (

            item["document"],

            item["chunk_number"]

        )

        if key not in merged:

            merged[key] = item

    candidates = list(merged.values())

    if settings.ENABLE_RERANKER:
        with timed_stage("reranking", candidates=len(candidates)):
            final = rerank_chunks(question, candidates, top_k=effective_top_k)
    else:
        final = candidates[:effective_top_k]

    cache.set(cache_key, final, settings.RETRIEVAL_CACHE_TTL)

    logger.info(
        "[PERF] retrieve_chunks TOTAL %8.1fms cache=miss vector=%d bm25=%d graph=%d hyde=%d multi_query=%d merged=%d final=%d",
        overall_timer.stop(), len(vector_results), len(bm25_results), len(graph_results),
        len(hyde_results), len(multi_query_results), len(candidates), len(final),
    )

    return final
