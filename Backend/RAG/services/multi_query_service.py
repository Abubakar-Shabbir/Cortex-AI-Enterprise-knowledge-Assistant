"""
Multi-query Retrieval (RAG-Fusion style).

Generates several alternate phrasings of the question
(query_transform_service), retrieves independently for each variant
using the existing vector_search()/bm25_search() - reused, not
reimplemented - then fuses the ranked result lists with Reciprocal
Rank Fusion (RRF) so chunks found by multiple variants, or found near
the top by any one of them, outrank one-off matches.
"""

import logging
from collections import defaultdict
from typing import Optional

from django.conf import settings

from .bm25_service import bm25_search
from .query_transform_service import generate_query_variants
from .retrieval_service import vector_search

logger = logging.getLogger(__name__)

# Standard RRF damping constant (Cormack et al., 2009) - large enough
# that rank differences among top results matter more than which list
# a result came from.
RRF_K = 60


def _reciprocal_rank_fusion(ranked_lists: list, top_k: int) -> list:
    """
    Fuse several ranked lists of result dicts (each already sorted
    best-first) into one ranked list. Each (document, chunk_number)
    is scored by sum(1 / (RRF_K + rank)) across every list it appears
    in, so a chunk found near the top of several variants' results
    outranks one found only once, and by only one variant.
    """

    scores: dict = defaultdict(float)
    items: dict = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, start=1):
            key = (item["document"], item["chunk_number"])
            scores[key] += 1.0 / (RRF_K + rank)
            items.setdefault(key, item)

    fused = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)

    results = []

    for key, score in fused[:top_k]:
        item = dict(items[key])
        item["score"] = round(score, 6)
        item["search_type"] = "multi_query"
        results.append(item)

    return results


def multi_query_search(
    question: str,
    top_k: Optional[int] = None,
    filters=None,
    num_variants: Optional[int] = None,
    user=None,
    accessible_document_ids=None,
) -> list:
    """
    Retrieve using several LLM-generated phrasings of `question` in
    addition to the original, fusing per-variant vector+BM25 results
    with Reciprocal Rank Fusion.

    Returns [] on any failure, or if no additional variants could be
    generated - this is purely additive to the existing hybrid
    pipeline (vector_search()/bm25_search() on the original question
    still run separately), never a replacement for it.

    `user` is forwarded to vector_search()/bm25_search() unchanged -
    both fail closed (return []) without it, so an omitted `user`
    here simply yields no fused results rather than searching every
    user's chunks. `accessible_document_ids`, when provided (e.g. by
    retrieve_chunks(), which computes it once for the whole hybrid
    retrieval call), is forwarded the same way so each variant's
    vector_search()/bm25_search() call doesn't re-derive it.
    """

    top_k = top_k or settings.TOP_K
    num_variants = num_variants or settings.MULTI_QUERY_VARIANTS

    try:
        variants = generate_query_variants(question, num_variants=num_variants)
    except Exception:
        logger.exception("Multi-query retrieval: variant generation failed")
        return []

    # variants[0] is always the original question (see
    # query_transform_service.generate_query_variants), already
    # covered by the primary vector_search()/bm25_search() calls
    # elsewhere in the pipeline - only the *additional* variants are
    # searched here.
    extra_variants = variants[1:]

    if not extra_variants:
        return []

    ranked_lists = []

    for variant in extra_variants:

        try:
            ranked_lists.append(vector_search(
                variant, top_k=top_k, filters=filters, user=user,
                accessible_document_ids=accessible_document_ids,
            ))
            ranked_lists.append(bm25_search(
                variant, top_k, filters=filters, user=user,
                accessible_document_ids=accessible_document_ids,
            ))
        except Exception:
            logger.exception(
                "Multi-query retrieval: search failed for variant %r", variant
            )

    if not ranked_lists:
        return []

    results = _reciprocal_rank_fusion(ranked_lists, top_k)

    logger.info(
        "Multi-query retrieval: %d variant(s) -> %d fused result(s)",
        len(extra_variants), len(results),
    )

    return results
