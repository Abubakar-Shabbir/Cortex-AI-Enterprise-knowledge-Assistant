import logging

from django.conf import settings
from pgvector.django import L2Distance

from ..models import ChunkEmbedding
from .embedding_service import generate_embedding
from .bm25_service import bm25_search
from .dynamic_topk_service import compute_dynamic_top_k
from .graph_retrieval_service import graph_search
from .hyde_service import generate_hypothetical_document
from .query_expansion_service import expand_query
from .reranker_service import rerank_chunks
from .retrieval_filters import apply_document_filters

logger = logging.getLogger(__name__)


def _vector_similarity_search(embedding, top_k, search_type="vector", filters=None):
    """
    Shared pgvector L2Distance nearest-neighbor lookup. Both
    vector_search() (embeds the question) and hyde_search() (embeds a
    generated hypothetical passage) are the same query over
    ChunkEmbedding once you already have an embedding vector - this is
    the one place that runs it, tagged with whichever `search_type`
    the caller is using it for.
    """

    queryset = ChunkEmbedding.objects.annotate(
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


def vector_search(question, top_k=None, filters=None):
    """
    Semantic Vector Search
    """

    query_embedding = generate_embedding(question)

    return _vector_similarity_search(
        query_embedding,
        top_k or settings.TOP_K,
        search_type="vector",
        filters=filters,
    )


def hyde_search(question, top_k=None, filters=None):
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

    hypothetical_embedding = generate_embedding(hypothetical_document)

    return _vector_similarity_search(
        hypothetical_embedding,
        top_k or settings.TOP_K,
        search_type="hyde",
        filters=filters,
    )


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
    """

    effective_top_k = top_k or (
        compute_dynamic_top_k(question)
        if settings.ENABLE_DYNAMIC_TOP_K
        else settings.TOP_K
    )

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
    lexical_query = (
        expand_query(question) if settings.ENABLE_QUERY_EXPANSION else question
    )

    vector_results = vector_search(question, top_k=retrieval_top_k, filters=filters)

    bm25_results = bm25_search(

        lexical_query,

        retrieval_top_k,

        filters=filters,

    )

    graph_results = graph_search(

        question,

        user,

        retrieval_top_k,

        filters=filters,

    )

    hyde_results = []

    if settings.ENABLE_HYDE:
        hyde_results = hyde_search(question, top_k=retrieval_top_k, filters=filters)

    multi_query_results = []

    if settings.ENABLE_MULTI_QUERY:
        # Imported here, not at module level, to avoid a circular
        # import: multi_query_service reuses this module's
        # vector_search() and bm25_service.bm25_search() directly
        # rather than duplicating retrieval logic.
        from .multi_query_service import multi_query_search

        multi_query_results = multi_query_search(
            question, top_k=retrieval_top_k, filters=filters
        )

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
        return rerank_chunks(question, candidates, top_k=effective_top_k)

    return candidates[:effective_top_k]
