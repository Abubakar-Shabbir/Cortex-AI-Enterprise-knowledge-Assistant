"""
BGE Reranker (cross-encoder re-scoring of retrieved chunks).

Hybrid retrieval (vector/BM25/graph/HyDE/multi-query) scores each chunk
independently of the question and of every other chunk - a pgvector
distance, a BM25 score, an entity match - so the merged candidate list
is only a rough approximation of relevance. A cross-encoder reranker
scores each (question, chunk) pair jointly instead, which is a
stronger relevance signal, at the cost of one local model inference
pass per candidate chunk.

Uses sentence-transformers' CrossEncoder (already a project dependency
via embedding_service.py) loading BAAI/bge-reranker-base by default -
no new third-party package required.
"""

import logging
from typing import Any, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

_reranker_model = None


def _get_reranker_model():
    """
    Lazily load and cache the cross-encoder reranker model.

    Loaded on first actual use rather than at import time (unlike
    embedding_service.py's eager `SentenceTransformer(...)` load), so
    that importing this module - which retrieval_service.py does
    unconditionally - never pays the model download/load cost while
    settings.ENABLE_RERANKER is off, preserving default request
    latency.
    """

    global _reranker_model

    if _reranker_model is None:

        from sentence_transformers import CrossEncoder

        _reranker_model = CrossEncoder(settings.RERANKER_MODEL)

    return _reranker_model


def rerank_chunks(
    question: str,
    chunks: list[dict[str, Any]],
    top_k: Optional[int] = None,
) -> list[dict[str, Any]]:
    """
    Reorder `chunks` by cross-encoder relevance to `question`.

    Each returned chunk dict is a shallow copy of the input with an
    added "rerank_score" key (higher is more relevant); all existing
    keys, including "search_type", are preserved unchanged so callers
    downstream (confidence scoring, search-method labeling, templates)
    keep working without modification. Truncates to `top_k` when given.

    Never raises - like the rest of the Sprint 5/6 retrieval services,
    any failure (model load error, inference error) is logged and the
    original `chunks` list is returned unchanged/unranked, so a
    reranker problem never breaks question answering.
    """

    if not chunks:
        return chunks

    try:
        model = _get_reranker_model()

        pairs = [[question, chunk["content"]] for chunk in chunks]

        scores = model.predict(pairs)

        reranked = sorted(
            zip(chunks, scores),
            key=lambda pair: pair[1],
            reverse=True,
        )

        results = []

        for chunk, score in reranked:

            reranked_chunk = dict(chunk)
            reranked_chunk["rerank_score"] = round(float(score), 4)
            results.append(reranked_chunk)

    except Exception:
        logger.exception("Reranking failed for question=%r; returning original order", question)
        return chunks[:top_k] if top_k else chunks

    return results[:top_k] if top_k else results
