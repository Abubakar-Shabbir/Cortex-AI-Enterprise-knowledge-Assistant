import logging
import threading

from langchain_core.embeddings import Embeddings
from django.conf import settings

from .perf import timed_stage

logger = logging.getLogger(__name__)

_model = None
_model_lock = threading.Lock()

_warmup_started = False
_warmup_lock = threading.Lock()


def _get_model():
    """
    Lazily load and cache the SentenceTransformer embedding model.

    Loaded on first actual use rather than at import time. This used
    to be a module-level `SentenceTransformer(...)` call, which meant
    importing this module - which happens unconditionally, during
    Django's own WSGI app import, since retrieval_service.py/
    upload_service.py/semantic_chunk_service.py all import it - paid
    the full model download/load cost synchronously before the process
    could even bind to a port. On a host like Railway, that's long
    enough to blow past the deploy health check window and surface as
    an upstream/timeout error, not a slow request. See
    ensure_warm_started() for what actually loads it in practice -
    almost always before a real request needs it.

    A lock guards construction so a real request that arrives while
    the warm-up thread is still loading waits on that same load
    instead of starting a second, redundant one - same pattern as
    reranker_service._get_reranker_model().
    """

    global _model

    if _model is None:
        with _model_lock:
            if _model is None:
                from sentence_transformers import SentenceTransformer

                _model = SentenceTransformer(settings.EMBEDDING_MODEL)

    return _model


def ensure_warm_started():
    """
    Kicks off loading the embedding model on a background thread pool
    worker (RAG.services.task_runner) the first time this is called in
    a process, instead of paying that cost inline on the first real
    upload/question - or, before this fix, at import time (see
    _get_model's docstring).

    Unlike reranker_service.ensure_warm_started(), this isn't gated
    behind a feature flag: embeddings are on the critical path for
    every upload and every query, not an opt-in extra, so this always
    warms. Called from RAG.middleware.SystemConfigSyncMiddleware on
    every request - cheap after the first call (a boolean check) - the
    same shape the reranker's warm-up already uses.
    """

    global _warmup_started

    if _warmup_started:
        return

    with _warmup_lock:
        if _warmup_started:
            return

        _warmup_started = True

        from .task_runner import submit

        submit(_get_model)


def generate_embedding(text):
    """
    Generate multilingual embedding using BGE-M3.
    """

    with timed_stage("embedding generation", chars=len(text or "")):
        embedding = _get_model().encode(
            text,
            normalize_embeddings=True
        )

    return embedding


class SharedSentenceTransformerEmbeddings(Embeddings):
    """
    Thin langchain_core.embeddings.Embeddings adapter around the one
    lazily-loaded SentenceTransformer instance above, so any LangChain
    component that needs an `Embeddings` object (e.g.
    semantic_chunk_service.py's SemanticChunker) reuses it instead of
    loading a second copy of the same model under a different library.
    """

    def embed_documents(self, texts):
        return _get_model().encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, text):
        return _get_model().encode(text, normalize_embeddings=True).tolist()


shared_embeddings = SharedSentenceTransformerEmbeddings()
