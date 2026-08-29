"""
Analytics endpoint for the React SPA - thin JSON wrapper around
RAG.views.analytics_view's exact same service calls
(stats_service.get_analytics_data/get_document_type_breakdown,
observability_service.get_performance_summary). No new aggregation
logic - every number here is computed by the same functions the
classic page already uses.
"""

from rest_framework.decorators import api_view, permission_classes

from rest_framework.response import Response

from ..services import observability_service
from ..services.permission_service import user_has_permission
from ..services.stats_service import get_analytics_data, get_document_type_breakdown
from .permissions import HasPagePermission


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.analytics")])
def analytics_view(request):
    data = get_analytics_data(request.user)

    can_view_all = user_has_permission(request.user, "analytics.view_all")
    ai_performance = observability_service.get_performance_summary(
        {} if can_view_all else {"user_id": request.user.id}
    )

    return Response({
        "data": data,
        "ai_performance": ai_performance,
        "document_types": get_document_type_breakdown(request.user),
        "can_view_ai_tasks": user_has_permission(request.user, "pages.ai_tasks"),
        "can_view_knowledge_base": user_has_permission(request.user, "pages.knowledge_base"),
    })
