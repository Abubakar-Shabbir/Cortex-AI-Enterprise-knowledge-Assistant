"""Search History endpoint for the React SPA - thin JSON wrapper around RAG.views.search_history's exact same query/pagination."""

from django.core.paginator import Paginator
from rest_framework.decorators import api_view, permission_classes

from rest_framework.response import Response

from ..models import QueryLog
from ..services.prompt_templates import is_not_found_answer
from .permissions import HasPagePermission


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.ask_ai")])
def search_history_view(request):
    logs = QueryLog.objects.filter(user=request.user).order_by("-created_at")

    history_rows = [
        {
            "question": log.question,
            "created_at": log.created_at,
            "documents_used": sorted({source.get("document") for source in (log.sources or []) if source.get("document")}),
            "response_time_ms": log.response_time_ms,
            "answered": not is_not_found_answer(log.answer),
        }
        for log in logs
    ]

    paginator = Paginator(history_rows, 15)
    page_obj = paginator.get_page(request.query_params.get("page"))

    return Response({
        "results": list(page_obj),
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "count": paginator.count,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
    })
