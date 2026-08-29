"""
Context Compression.

Hybrid retrieval merges up to five independently-scored sources
(vector/BM25/graph/HyDE/multi-query), so the same idea is often
retrieved more than once - the same fact paraphrased across two
chunks, or two chunks that overlap because of CHUNK_OVERLAP. Passing
every retrieved chunk to the LLM wastes context budget and can dilute
the answer with repeated wording, without adding information.

compress_context() drops chunks that are semantically redundant with
one already kept, using cosine similarity between chunk embeddings.
It reuses embedding_service.generate_embedding() - the same
SentenceTransformer instance the upload/query pipeline already loads
- so this adds no new dependency and no LLM call. It only ever drops
a *later* near-duplicate, never the first occurrence of an idea, so
every distinct fact retrieved still reaches the LLM - just without
duplicates padding the context.
"""

import logging
from typing import Any, Optional

import numpy as np

from .embedding_service import generate_embedding

logger = logging.getLogger(__name__)

DEFAULT_SIMILARITY_THRESHOLD = 0.92


def _cosine_similarity(vector_a, vector_b) -> float:

    vector_a = np.asarray(vector_a)
    vector_b = np.asarray(vector_b)

    denominator = np.linalg.norm(vector_a) * np.linalg.norm(vector_b)

    if denominator == 0:
        return 0.0

    return float(np.dot(vector_a, vector_b) / denominator)


def compress_context(
    chunks: list[dict[str, Any]],
    similarity_threshold: Optional[float] = None,
) -> list[dict[str, Any]]:
    """
    Return `chunks` with semantically redundant entries removed.

    Walks `chunks` in order - retrieval/rerank priority is preserved,
    the same "first occurrence wins" rule retrieve_chunks() already
    uses for exact (document, chunk_number) duplicates - and drops a
    chunk only when its cosine similarity to some already-kept chunk
    is >= `similarity_threshold` (defaults to
    settings.CONTEXT_COMPRESSION_THRESHOLD). Kept chunks are returned
    as-is (not copies); fewer than 2 chunks is returned unchanged
    since there is nothing to compare.

    Never raises: any failure (embedding error) is logged and the
    original `chunks` list is returned unchanged, so a compression
    problem never breaks question answering.
    """

    if len(chunks) < 2:
        return chunks

    if similarity_threshold is None:
        from django.conf import settings

        similarity_threshold = settings.CONTEXT_COMPRESSION_THRESHOLD

    try:
        embeddings = [generate_embedding(chunk["content"]) for chunk in chunks]
    except Exception:
        logger.exception("Context compression: embedding failed, skipping compression")
        return chunks

    kept = []
    kept_embeddings = []

    for chunk, embedding in zip(chunks, embeddings):

        is_redundant = any(
            _cosine_similarity(embedding, kept_embedding) >= similarity_threshold
            for kept_embedding in kept_embeddings
        )

        if is_redundant:
            continue

        kept.append(chunk)
        kept_embeddings.append(embedding)

    removed = len(chunks) - len(kept)

    if removed:
        logger.info(
            "Context compression: removed %d redundant chunk(s) of %d",
            removed,
            len(chunks),
        )

    return kept
