import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from rank_bm25 import BM25Okapi

from ..models import DocumentChunk
from .document_access_service import get_accessible_document_ids
from .perf import timed_stage
from .retrieval_filters import apply_document_filters

logger = logging.getLogger(__name__)


def _bm25_cache_key(accessible_ids, filters):
    """
    Fingerprints the viewer's accessible scope (+ how many chunks
    currently exist within it, + any active filters) so the cached
    BM25 index self-invalidates on the events that actually matter -
    a new document, newly-embedded chunks, a different filter - without
    needing explicit signal/hook wiring. See settings.RETRIEVAL_CACHE_TTL's
    docstring for the staleness window this still leaves open (editing
    an existing chunk's content in place - a feature this app doesn't
    have).

    The whole fingerprint is hashed (not embedded raw into the key, as
    an earlier version did) - a real `RetrievalFilters` instance's
    `repr()` contains spaces and can run long, which trips Django's
    `CacheKeyWarning` (memcached-incompatible key) on every call with
    an active filters object - i.e. every real Ask AI submission, since
    RetrievalFilters.from_request() always builds a real instance even
    when nothing is actually filtered. Hashing sidesteps that and keeps
    the key a fixed, predictable length regardless of how large
    `filters.document_ids` gets. Note this key is per-process under the
    default LocMemCache backend - a multi-worker deployment needs
    settings.USE_REDIS_CACHE=True for the cache to actually be shared
    across workers, or a repeat question landing on a different worker
    than the one that cached it looks like a permanent miss.
    """

    chunk_count = DocumentChunk.objects.filter(document_id__in=accessible_ids).count()
    ids_fingerprint = hashlib.sha256(",".join(str(i) for i in sorted(accessible_ids)).encode()).hexdigest()
    raw = f"{ids_fingerprint}:{chunk_count}:{filters!r}"

    return "bm25_index:" + hashlib.sha256(raw.encode()).hexdigest()


def bm25_search(
    question,
    top_k,
    filters=None,
    user=None,
    accessible_document_ids=None,
):
    """
    Perform BM25 keyword search over `user`'s accessible document
    chunks (owned + Organization Library + shared-with-them - see
    document_access_service).

    `user` is required for a non-empty result - a missing `user`
    fails closed (returns []) rather than indexing every user's
    chunks, matching graph_search()'s existing precedent.

    `accessible_document_ids`, when provided, is used as-is instead of
    recomputing it here - lets retrieve_chunks() compute it once and
    share it across vector/BM25/graph search.

    The built BM25Okapi index (the expensive part - loading every
    accessible chunk and tokenizing the whole corpus) is cached per
    accessible-scope for settings.RETRIEVAL_CACHE_TTL seconds -
    previously this rebuilt from scratch on every single call
    regardless of whether the underlying documents had changed at all.

    Never raises - delegates to _bm25_search_impl() inside a try/except
    so a failure (e.g. a corrupt cached index) degrades to no BM25
    contribution, matching vector_search()/graph_search()'s contract,
    instead of propagating uncaught through retrieve_chunks()'s thread
    pool into a raw 500 for the whole request.
    """

    if user is None:
        return []

    try:
        return _bm25_search_impl(question, top_k, filters, user, accessible_document_ids)
    except Exception:
        logger.exception("BM25 search failed")
        return []


def _bm25_search_impl(question, top_k, filters, user, accessible_document_ids=None):
    accessible_ids = (
        accessible_document_ids if accessible_document_ids is not None else get_accessible_document_ids(user)
    )

    if not accessible_ids:
        return []

    cache_key = _bm25_cache_key(accessible_ids, filters)
    cached = cache.get(cache_key)

    if cached is None:

        with timed_stage("BM25 index build (cache miss)", accessible_docs=len(accessible_ids)):

            # -------------------------
            # Load All Chunks
            # -------------------------

            chunks_queryset = DocumentChunk.objects.filter(document_id__in=accessible_ids).select_related(
                "document"
            )

            chunks_queryset = apply_document_filters(
                chunks_queryset, filters, document_field="document"
            )

            chunks = list(chunks_queryset)

            # -------------------------
            # Tokenize + Build BM25 Index
            # -------------------------

            bm25 = None

            if chunks:

                corpus = [

                    chunk.content.lower().split()

                    for chunk in chunks

                ]

                bm25 = BM25Okapi(
                    corpus
                )

        cache.set(cache_key, (bm25, chunks), settings.RETRIEVAL_CACHE_TTL)

    else:
        bm25, chunks = cached

    if not chunks or bm25 is None:
        return []

    with timed_stage("BM25 scoring", corpus_size=len(chunks)):

        # -------------------------
        # Tokenize Query + Score
        # -------------------------

        query = question.lower().split()

        scores = bm25.get_scores(
            query
        )

        ranked = sorted(

            zip(chunks, scores),

            key=lambda x: x[1],

            reverse=True

        )

    # -------------------------
    # Build Response
    # -------------------------

    results = []

    for chunk, score in ranked[:top_k]:

        results.append(

            {

                "content": chunk.content,

                "document": chunk.document.title,

                "chunk_number": chunk.chunk_number,

                "score": round(float(score), 4),

                "search_type": "bm25",

            }

        )

    return results
