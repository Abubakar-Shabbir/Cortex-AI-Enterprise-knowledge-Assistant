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

Performance notes (why this file looks the way it does)
---------------------------------------------------------
A live profile of the default configuration showed reranking 23
candidates taking ~11s, for two compounding reasons:

1. The model was never warmed up, so the first question to actually
   need it paid the full model download/load cost (several seconds)
   inline, inside that request's "reranking" stage. `ensure_warm_started()`
   below moves that cost to a background thread the first time this
   process handles a request, instead of a user's first question.
2. `CrossEncoder.predict()` was called with no `max_length`, so it fell
   back to the tokenizer's own default (512 for bge-reranker-base) and
   padded every pair in the batch to the longest sequence present - one
   unusually long chunk drags the whole batch's compute up with it.
   `settings.RERANKER_MAX_LENGTH` bounds that; normal chunks (~150-220
   tokens) never hit it.

Neither the model, the candidate pool, nor the final top-k behavior
changed - see retrieval_service.py, which is untouched.
"""

import logging
import os
import threading
from typing import Any, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

_reranker_model = None
_reranker_model_lock = threading.Lock()

_warmup_started = False
_warmup_lock = threading.Lock()

_threads_configured = False


def _configure_torch_threads():
    """
    Uses every available CPU core for intra-op parallelism, once per
    process. Only matters on CPU (a GPU deployment ignores this) and
    is defensive - a failure here (e.g. an unusual torch build) just
    means the process keeps whatever thread count it already had, not
    a broken reranker.
    """

    global _threads_configured

    if _threads_configured:
        return

    _threads_configured = True

    try:
        import torch

        cpu_count = os.cpu_count() or 1
        if torch.get_num_threads() < cpu_count:
            torch.set_num_threads(cpu_count)
    except Exception:
        logger.exception("Failed to configure torch thread count for reranker")


def _get_reranker_model():
    """
    Lazily load and cache the cross-encoder reranker model.

    Loaded on first actual use rather than at import time (unlike
    embedding_service.py's eager `SentenceTransformer(...)` load), so
    that importing this module - which retrieval_service.py does
    unconditionally - never pays the model download/load cost while
    settings.ENABLE_RERANKER is off, preserving default request
    latency. In practice that first use is almost always
    ensure_warm_started()'s background thread rather than a real
    question - see the module docstring.

    A lock guards construction so a real question that arrives while
    the warm-up thread is still loading the model waits on that same
    load instead of starting a second, redundant one.
    """

    global _reranker_model

    if _reranker_model is None:
        with _reranker_model_lock:
            if _reranker_model is None:

                _configure_torch_threads()

                from sentence_transformers import CrossEncoder

                _reranker_model = CrossEncoder(
                    settings.RERANKER_MODEL,
                    max_length=settings.RERANKER_MAX_LENGTH,
                )

    return _reranker_model


def ensure_warm_started():
    """
    Kicks off loading the reranker model on a background thread pool
    worker (RAG.services.task_runner) the first time this is called in
    a process, instead of letting the first real question pay that
    cost inline. A no-op once already started (module-level flag) and
    a no-op entirely when settings.ENABLE_RERANKER is off, so it costs
    nothing on a deployment that doesn't use reranking.

    Called from RAG.middleware.SystemConfigSyncMiddleware on every
    request (cheap after the first - a settings check plus a boolean
    check), not from AppConfig.ready() - ready() also runs for
    management commands (migrate, makemigrations, test, ...), and
    warming a several-hundred-MB model in the background on every
    `manage.py` invocation would be wasteful. Going through a request
    means this only ever fires for an actual running server.
    """

    global _warmup_started

    if _warmup_started or not settings.ENABLE_RERANKER:
        return

    with _warmup_lock:
        if _warmup_started:
            return

        _warmup_started = True

        from .task_runner import submit

        submit(_get_reranker_model)


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

        scores = model.predict(
            pairs,
            batch_size=settings.RERANKER_BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
        )

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
