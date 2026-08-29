"""
/api/admin/settings/ - Admin > Settings (RAG pipeline configuration).
Thin DRF wrapper around RAG.views.admin_settings_view /
llm_provider_health_check - reuses system_config_service.get_config()/
save_config() and get_llm().health_check() verbatim rather than
reimplementing any of that logic.
"""

from django.conf import settings
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from ..services.activity_log_service import log_activity
from ..services.llm_client import get_llm
from ..services.permission_service import has_any_settings_permission, user_has_permission
from ..services.stats_service import get_system_status
from ..services.system_config_service import SettingsValidationError, get_config, get_llm_provider_options, save_config


class _HasAnySettingsPermission(BasePermission):
    message = "You don't have access to this resource."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated and has_any_settings_permission(request.user)
        )


def _serialize_config(config, request):
    return {
        "llm_provider": config.llm_provider,
        "enable_fallback": config.enable_fallback,
        "openrouter_model": config.openrouter_model,
        "groq_model": config.groq_model,
        "gemini_model": config.gemini_model,
        "top_k": config.top_k,
        "answer_temperature": config.answer_temperature,
        "chunk_size": config.chunk_size,
        "chunk_overlap": config.chunk_overlap,
        "enable_query_expansion": config.enable_query_expansion,
        "enable_hyde": config.enable_hyde,
        "enable_multi_query": config.enable_multi_query,
        "multi_query_variants": config.multi_query_variants,
        "enable_dynamic_top_k": config.enable_dynamic_top_k,
        "dynamic_top_k_max": config.dynamic_top_k_max,
        "enable_reranker": config.enable_reranker,
        "reranker_candidate_multiplier": config.reranker_candidate_multiplier,
        "enable_context_compression": config.enable_context_compression,
        "context_compression_threshold": config.context_compression_threshold,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
        "updated_by": config.updated_by.username if config.updated_by else None,
    }


@api_view(["GET", "POST"])
@permission_classes([_HasAnySettingsPermission])
def admin_settings_view(request):
    config = get_config()

    if request.method == "POST":
        payload = request.data

        try:
            data = {
                "llm_provider": payload.get("llm_provider", config.llm_provider),
                "enable_fallback": bool(payload.get("enable_fallback", config.enable_fallback)),
                "openrouter_model": (payload.get("openrouter_model") or config.openrouter_model).strip() or config.openrouter_model,
                "groq_model": (payload.get("groq_model") or config.groq_model).strip() or config.groq_model,
                "gemini_model": (payload.get("gemini_model") or config.gemini_model).strip() or config.gemini_model,
                "top_k": int(payload.get("top_k", config.top_k)),
                "answer_temperature": float(payload.get("answer_temperature", config.answer_temperature)),
                "chunk_size": int(payload.get("chunk_size", config.chunk_size)),
                "chunk_overlap": int(payload.get("chunk_overlap", config.chunk_overlap)),
                "enable_query_expansion": bool(payload.get("enable_query_expansion", config.enable_query_expansion)),
                "enable_hyde": bool(payload.get("enable_hyde", config.enable_hyde)),
                "enable_multi_query": bool(payload.get("enable_multi_query", config.enable_multi_query)),
                "multi_query_variants": int(payload.get("multi_query_variants", config.multi_query_variants)),
                "enable_dynamic_top_k": bool(payload.get("enable_dynamic_top_k", config.enable_dynamic_top_k)),
                "dynamic_top_k_max": int(payload.get("dynamic_top_k_max", config.dynamic_top_k_max)),
                "enable_reranker": bool(payload.get("enable_reranker", config.enable_reranker)),
                "reranker_candidate_multiplier": int(payload.get("reranker_candidate_multiplier", config.reranker_candidate_multiplier)),
                "enable_context_compression": bool(payload.get("enable_context_compression", config.enable_context_compression)),
                "context_compression_threshold": float(payload.get("context_compression_threshold", config.context_compression_threshold)),
            }
        except (TypeError, ValueError):
            return Response({"errors": ["Some values were invalid - nothing was saved."]}, status=400)

        try:
            save_config(data, request.user)
        except SettingsValidationError as exc:
            return Response({"errors": exc.errors}, status=400)

        log_activity(
            actor=request.user,
            action="settings.updated",
            description=f"RAG pipeline configuration updated by {request.user.username}",
            request=request,
        )

        config = get_config()

    return Response({
        "config": _serialize_config(config, request),
        "system_status": get_system_status(),
        "db_name": settings.DATABASES["default"]["NAME"],
        "db_host": settings.DATABASES["default"]["HOST"],
        "llm_provider_options": get_llm_provider_options(config),
        "can_edit_any": any(
            user_has_permission(request.user, code)
            for code in ("settings.manage_llm", "settings.manage_chunking", "settings.manage_retrieval")
        ),
        "user_permissions": [
            code for code in (
                "settings.manage_llm", "settings.manage_embedding", "settings.manage_chunking",
                "settings.manage_database", "settings.manage_retrieval",
            ) if user_has_permission(request.user, code)
        ],
    })


@api_view(["POST"])
@permission_classes([_HasAnySettingsPermission])
def llm_provider_health_check_view(request):
    if not user_has_permission(request.user, "settings.manage_llm"):
        return Response({"error": "Forbidden"}, status=403)

    provider = request.data.get("provider", "")
    result = get_llm().health_check(provider)

    return Response(result)
