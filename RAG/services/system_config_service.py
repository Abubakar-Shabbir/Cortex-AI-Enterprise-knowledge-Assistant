"""
System Configuration Service

The only code that should read/write RAG.models.SystemConfiguration
directly. Values here are applied on top of settings.py at runtime
(apply_config_to_settings()) rather than replacing it - every existing
consumer of settings.TOP_K / settings.ENABLE_HYDE / etc. across
retrieval_service.py, dynamic_topk_service.py, multi_query_service.py,
context_compression_service.py, query_service.py, and
document_processor.py keeps working completely unchanged, because
Django's settings object is a live attribute lookup: patching
settings.TOP_K here is visible to every one of those "from django.conf
import settings; settings.TOP_K" reads immediately, with zero changes
to any of those files.

Multi-process deployments (e.g. several gunicorn workers) don't share
this process's monkey-patched settings object, so apply_config_to_settings()
is re-run on a short cache TTL (see RAG.middleware.SystemConfigSyncMiddleware)
rather than only once at startup - the same cache.get_or_set(..., 30)
pattern context_processors.sidebar_status() already uses for
system_status, just applied to settings instead of a template context.
"""

import logging

from django.conf import settings
from django.core.cache import cache

from ..models import SystemConfiguration

logger = logging.getLogger(__name__)

CONFIG_CACHE_KEY = "rag_system_configuration_applied"
CONFIG_CACHE_TTL = 15

# Field name -> settings.py attribute name this field overrides.
MANAGED_SETTINGS_FIELDS = [
    ("llm_provider", "LLM_PROVIDER"),
    ("top_k", "TOP_K"),
    ("answer_temperature", "ANSWER_TEMPERATURE"),
    ("chunk_size", "CHUNK_SIZE"),
    ("chunk_overlap", "CHUNK_OVERLAP"),
    ("enable_query_expansion", "ENABLE_QUERY_EXPANSION"),
    ("enable_hyde", "ENABLE_HYDE"),
    ("enable_multi_query", "ENABLE_MULTI_QUERY"),
    ("multi_query_variants", "MULTI_QUERY_VARIANTS"),
    ("enable_dynamic_top_k", "ENABLE_DYNAMIC_TOP_K"),
    ("dynamic_top_k_max", "DYNAMIC_TOP_K_MAX"),
    ("enable_reranker", "ENABLE_RERANKER"),
    ("reranker_candidate_multiplier", "RERANKER_CANDIDATE_MULTIPLIER"),
    ("enable_context_compression", "ENABLE_CONTEXT_COMPRESSION"),
    ("context_compression_threshold", "CONTEXT_COMPRESSION_THRESHOLD"),
]


def get_config():
    """
    The singleton SystemConfiguration row, creating it on first access
    seeded from settings.py's own current values - so turning this
    feature on doesn't silently reset a workspace's existing .env
    configuration back to this model's hardcoded field defaults.
    """

    config, _ = SystemConfiguration.objects.get_or_create(
        pk=1,
        defaults={
            "llm_provider": settings.LLM_PROVIDER,
            "top_k": settings.TOP_K,
            "answer_temperature": settings.ANSWER_TEMPERATURE,
            "chunk_size": settings.CHUNK_SIZE,
            "chunk_overlap": settings.CHUNK_OVERLAP,
            "enable_query_expansion": settings.ENABLE_QUERY_EXPANSION,
            "enable_hyde": settings.ENABLE_HYDE,
            "enable_multi_query": settings.ENABLE_MULTI_QUERY,
            "multi_query_variants": settings.MULTI_QUERY_VARIANTS,
            "enable_dynamic_top_k": settings.ENABLE_DYNAMIC_TOP_K,
            "dynamic_top_k_max": settings.DYNAMIC_TOP_K_MAX,
            "enable_reranker": settings.ENABLE_RERANKER,
            "reranker_candidate_multiplier": settings.RERANKER_CANDIDATE_MULTIPLIER,
            "enable_context_compression": settings.ENABLE_CONTEXT_COMPRESSION,
            "context_compression_threshold": settings.CONTEXT_COMPRESSION_THRESHOLD,
        },
    )
    return config


def apply_config_to_settings():
    """
    Patch the current process's django.conf.settings with the DB
    config's values. Never raises: on any failure (e.g. no DB
    connection yet during startup) this logs and leaves settings.py's
    own values in place rather than crashing app startup.
    """

    try:
        config = get_config()
    except Exception:
        logger.exception("Could not load SystemConfiguration - keeping settings.py defaults.")
        return

    for field_name, settings_name in MANAGED_SETTINGS_FIELDS:
        setattr(settings, settings_name, getattr(config, field_name))


def apply_config_to_settings_cached():
    """
    Same as apply_config_to_settings(), but skips the DB round trip if
    it already ran within CONFIG_CACHE_TTL seconds in this process -
    called on every request (RAG.middleware.SystemConfigSyncMiddleware)
    so a config change made by one worker process reaches the others
    within a bounded delay instead of requiring a restart.
    """

    if cache.get(CONFIG_CACHE_KEY):
        return

    apply_config_to_settings()
    cache.set(CONFIG_CACHE_KEY, True, CONFIG_CACHE_TTL)


def save_config(data, user):
    """
    Persist an admin's edits and apply them to this process
    immediately (not waiting for the cache TTL), so the admin who just
    saved sees the new behavior on their very next request.
    """

    config = get_config()

    for field_name, _ in MANAGED_SETTINGS_FIELDS:
        if field_name in data:
            setattr(config, field_name, data[field_name])

    config.updated_by = user
    config.save()

    cache.delete(CONFIG_CACHE_KEY)
    apply_config_to_settings()

    # LLMClient snapshots settings.LLM_PROVIDER at construction time
    # (see llm_client.py's own docstring on reset_llm_client) - every
    # other setting here is read fresh on each call, so only this one
    # needs an explicit cache-bust.
    from .llm_client import reset_llm_client
    reset_llm_client()

    return config
