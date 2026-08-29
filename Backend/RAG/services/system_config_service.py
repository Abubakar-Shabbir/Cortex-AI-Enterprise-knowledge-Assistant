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


class SettingsValidationError(Exception):
    """Raised by save_config() when the submitted values fail _validate() - carries every error message (not just the first) so the view can show all of them at once. Never partially applied: raised before config.save() is ever called, so a rejected submit leaves the DB row completely unchanged."""

    def __init__(self, errors):
        self.errors = errors
        super().__init__("; ".join(errors))


# (field name, settings.py attribute this field overrides, RBAC permission
# that must be held to edit it). The permission column is what lets
# admin_settings_view / save_config() scope both the template and the
# POST handler per field-group instead of the single all-or-nothing
# settings.manage_llm gate this page used to have - see seed_rbac.py for
# where these codenames are defined.
MANAGED_SETTINGS_FIELDS = [
    ("llm_provider", "LLM_PROVIDER", "settings.manage_llm"),
    ("enable_fallback", "LLM_FALLBACK_ENABLED", "settings.manage_llm"),
    ("openrouter_model", "OPENROUTER_MODEL", "settings.manage_llm"),
    ("groq_model", "GROQ_MODEL", "settings.manage_llm"),
    ("gemini_model", "LLM_MODEL", "settings.manage_llm"),
    ("answer_temperature", "ANSWER_TEMPERATURE", "settings.manage_llm"),
    ("top_k", "TOP_K", "settings.manage_chunking"),
    ("chunk_size", "CHUNK_SIZE", "settings.manage_chunking"),
    ("chunk_overlap", "CHUNK_OVERLAP", "settings.manage_chunking"),
    ("enable_query_expansion", "ENABLE_QUERY_EXPANSION", "settings.manage_retrieval"),
    ("enable_hyde", "ENABLE_HYDE", "settings.manage_retrieval"),
    ("enable_multi_query", "ENABLE_MULTI_QUERY", "settings.manage_retrieval"),
    ("multi_query_variants", "MULTI_QUERY_VARIANTS", "settings.manage_retrieval"),
    ("enable_dynamic_top_k", "ENABLE_DYNAMIC_TOP_K", "settings.manage_retrieval"),
    ("dynamic_top_k_max", "DYNAMIC_TOP_K_MAX", "settings.manage_retrieval"),
    ("enable_reranker", "ENABLE_RERANKER", "settings.manage_retrieval"),
    ("reranker_candidate_multiplier", "RERANKER_CANDIDATE_MULTIPLIER", "settings.manage_retrieval"),
    ("enable_context_compression", "ENABLE_CONTEXT_COMPRESSION", "settings.manage_retrieval"),
    ("context_compression_threshold", "CONTEXT_COMPRESSION_THRESHOLD", "settings.manage_retrieval"),
]

# Distinct permission codenames in MANAGED_SETTINGS_FIELDS, in card
# display order - the editable cards. save_config() filters incoming
# data by these.
FIELD_GROUP_PERMISSIONS = list(dict.fromkeys(perm for _, _, perm in MANAGED_SETTINGS_FIELDS))

# Every permission that gates *something* on the Settings page, editable
# or not - FIELD_GROUP_PERMISSIONS above plus manage_embedding/
# manage_database, which gate the two read-only info cards (Embedding
# Model, Database) that have no form fields at all, so they'd never
# appear in MANAGED_SETTINGS_FIELDS otherwise. permission_service
# .has_any_settings_permission() uses this full set to decide whether a
# user can open the page at all - someone holding only
# settings.manage_database should still see the Database card, even
# though there's nothing on it for them to edit.  settings.manage_api_keys
# is deliberately excluded: there is no key-viewing/rotating UI on this
# page at all (raw keys are env-var-only, by design), so that permission
# grants nothing here to see.
SETTINGS_PAGE_PERMISSIONS = FIELD_GROUP_PERMISSIONS + ["settings.manage_embedding", "settings.manage_database"]


def get_config():
    """
    The singleton SystemConfiguration row, creating it on first access
    seeded from settings.py's own current values - so turning this
    feature on doesn't silently reset a workspace's existing .eee
    configuration back to this model's hardcoded field defaults.
    """

    config, _ = SystemConfiguration.objects.get_or_create(
        pk=1,
        defaults={
            "llm_provider": settings.LLM_PROVIDER,
            "enable_fallback": settings.LLM_FALLBACK_ENABLED,
            "openrouter_model": settings.OPENROUTER_MODEL,
            "groq_model": settings.GROQ_MODEL,
            "gemini_model": settings.LLM_MODEL,
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

    for field_name, settings_name, _ in MANAGED_SETTINGS_FIELDS:
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


def get_llm_provider_options(config):
    """
    Per-provider metadata for the Settings page's LLM Configuration
    card: label, whether an API key is configured, and the model
    dropdown choices - the curated free-model list from
    llm_client.PROVIDER_REGISTRY, plus the currently-configured value
    appended if it isn't already one of them, so a custom value set
    directly via .eee is never silently dropped from the dropdown.
    """

    from .llm_client import PROVIDER_REGISTRY

    field_map = {"openrouter": "openrouter_model", "groq": "groq_model", "gemini": "gemini_model"}

    options = []

    for key, meta in PROVIDER_REGISTRY.items():

        field_name = field_map[key]
        current_model = getattr(config, field_name)
        choices = list(meta["free_models"])

        if current_model and current_model not in choices:
            choices.append(current_model)

        options.append({
            "key": key,
            "label": meta["label"],
            "configured": bool(getattr(settings, meta["api_key_setting"], "")),
            "field_name": field_name,
            "current_model": current_model,
            "model_choices": choices,
        })

    return options


def _validate(values: dict) -> list:
    """
    Cross-field/range checks that `.save()`'s Postgres CHECK constraints
    don't (and can't) express - e.g. a negative top_k hits the DB
    constraint, but there's no DB-level way to say "chunk_overlap must
    be smaller than chunk_size" or "temperature must be <= 1". `values`
    is the FULL proposed set of field values (existing config merged
    with whatever the caller is changing), so a partial edit (e.g. a
    manage_chunking-only user changing just chunk fields) still gets a
    complete, correct validation pass rather than only checking the
    fields that happen to be present in this particular submission.
    Returns a list of human-readable error strings - empty means valid.
    """

    from .llm_client import PROVIDER_REGISTRY

    errors = []

    if values["chunk_size"] < 100:
        errors.append("Chunk size must be at least 100 characters.")

    if values["chunk_overlap"] < 0 or values["chunk_overlap"] >= values["chunk_size"]:
        errors.append("Chunk overlap must be smaller than chunk size.")

    if not (0 <= values["answer_temperature"] <= 1):
        errors.append("Answer temperature must be between 0 and 1.")

    if not (0 <= values["context_compression_threshold"] <= 1):
        errors.append("Context compression threshold must be between 0 and 1.")

    if not (1 <= values["top_k"] <= 50):
        errors.append("Retrieval top-K must be between 1 and 50.")

    if not (1 <= values["dynamic_top_k_max"] <= 50):
        errors.append("Dynamic top-K max must be between 1 and 50.")

    if not (1 <= values["multi_query_variants"] <= 10):
        errors.append("Multi-query variants must be between 1 and 10.")

    if not (1 <= values["reranker_candidate_multiplier"] <= 10):
        errors.append("Reranker candidate multiplier must be between 1 and 10.")

    if values["llm_provider"] not in PROVIDER_REGISTRY:
        errors.append(f"Unknown LLM provider '{values['llm_provider']}'.")

    return errors


def save_config(data, user):
    """
    Persist an admin's edits and apply them to this process
    immediately (not waiting for the cache TTL), so the admin who just
    saved sees the new behavior on their very next request.

    Two safety layers before anything touches the DB:
    - RBAC: only fields whose MANAGED_SETTINGS_FIELDS permission `user`
      actually holds are applied - a field present in `data` without
      the matching permission is silently ignored (defense in depth;
      the view should already be filtering its POST handling by the
      same permissions, but this is "the only code that should read/
      write SystemConfiguration directly" per the module docstring, so
      it enforces its own boundary rather than trusting every caller).
    - Validation: raises SettingsValidationError (carrying every
      message) instead of calling .save() at all if the resulting
      values would be invalid - no partial writes, no bad value ever
      reaches the DB (previously a negative value on any Positive field
      hit Postgres's CHECK constraint as an uncaught IntegrityError).
    """

    from .permission_service import user_has_permission

    config = get_config()

    proposed = {field_name: getattr(config, field_name) for field_name, _, _ in MANAGED_SETTINGS_FIELDS}

    for field_name, _, permission in MANAGED_SETTINGS_FIELDS:
        if field_name in data and user_has_permission(user, permission):
            proposed[field_name] = data[field_name]

    errors = _validate(proposed)

    if errors:
        raise SettingsValidationError(errors)

    for field_name, value in proposed.items():
        setattr(config, field_name, value)

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
