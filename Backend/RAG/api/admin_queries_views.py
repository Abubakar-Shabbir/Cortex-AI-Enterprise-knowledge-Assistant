"""
Admin > Queries endpoints for the React SPA - thin JSON wrappers
around RAG.views.admin_queries_view/admin_query_detail_view/
admin_query_toggle_flag_view/export_queries_report's exact same
service calls (queries_service.py). Same privacy boundary: content
(question/answer/search text) requires "queries.view_content" on top
of "queries.view_all_logs", and every content-detail read is
audit-logged exactly like the classic view.
"""

import csv

from django.core.paginator import Paginator
from django.http import HttpResponse, HttpResponseNotAllowed
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..decorators import permission_required
from ..models import QueryLog
from ..services.activity_log_service import log_activity
from ..services.permission_service import user_has_permission
from ..services.queries_service import annotate_status, filter_and_sort_queries, get_queries_analytics, get_search_methods
from ..services.reports_service import QUERIES_REPORT_HEADER_METADATA, QUERIES_REPORT_HEADER_WITH_CONTENT, get_queries_report_rows
from .permissions import HasPagePermission


def _serialize_log(log):
    return {
        "id": log.id,
        "question": log.question,
        "owner": log.user.username,
        "status_answered": log.status_answered,
        "status_label": log.status_label,
        "search_method": log.search_method,
        "confidence": log.confidence,
        "response_time_ms": log.response_time_ms,
        "source_count": len(log.sources or []),
        "created_at": log.created_at,
        "is_flagged": log.is_flagged,
    }


@api_view(["GET"])
@permission_classes([HasPagePermission("queries.view_all_logs")])
def admin_queries_view(request):
    can_view_content = user_has_permission(request.user, "queries.view_content")

    params = request.query_params.copy()
    params["_content_search_allowed"] = can_view_content

    logs = filter_and_sort_queries(params, request_user=request.user)
    analytics = get_queries_analytics(logs)

    paginator = Paginator(logs, 20)
    page_obj = paginator.get_page(request.query_params.get("page"))
    annotate_status(page_obj.object_list)

    return Response({
        "results": [_serialize_log(log) for log in page_obj],
        "page": page_obj.number,
        "num_pages": paginator.num_pages,
        "count": paginator.count,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
        "analytics": analytics,
        "search_methods": get_search_methods(),
        "can_view_content": can_view_content,
    })


@api_view(["GET"])
@permission_classes([HasPagePermission("queries.view_all_logs", "queries.view_content")])
def admin_query_detail_view(request, log_id):
    log = QueryLog.objects.select_related("user").filter(id=log_id).first()
    if log is None:
        return Response({"error": "Not found."}, status=404)

    log_activity(
        actor=request.user, action="admin.query_content_viewed",
        description=f'{request.user.username} viewed the content of a query log by "{log.user.username}" (log #{log.id}) via Admin > Queries',
        request=request,
    )

    return Response({
        "id": log.id,
        "owner": log.user.username,
        "question": log.question,
        "answer": log.answer,
        "sources": log.sources,
        "search_method": log.search_method,
        "confidence": log.confidence,
        "response_time_ms": log.response_time_ms,
        "created_at": log.created_at.strftime("%Y-%m-%d %H:%M:%S"),
    })


@api_view(["POST"])
@permission_classes([HasPagePermission("queries.view_all_logs")])
def admin_query_toggle_flag_view(request, log_id):
    log = QueryLog.objects.filter(id=log_id).first()
    if log is None:
        return Response({"error": "Not found."}, status=404)
    log.is_flagged = not log.is_flagged
    log.save(update_fields=["is_flagged"])
    return Response({"id": log.id, "is_flagged": log.is_flagged})


@permission_required("queries.view_all_logs")
def export_queries_report_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])

    can_view_content = user_has_permission(request.user, "queries.view_content")
    params = request.GET.copy()
    params["_content_search_allowed"] = can_view_content
    logs = filter_and_sort_queries(params, request_user=request.user).select_related("user")

    if can_view_content:
        log_activity(
            actor=request.user, action="admin.query_content_exported",
            description=f"{request.user.username} exported {logs.count()} query log(s) including question/answer content via Admin > Queries",
            request=request,
        )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="queries_report.csv"'
    writer = csv.writer(response)
    writer.writerow(QUERIES_REPORT_HEADER_WITH_CONTENT if can_view_content else QUERIES_REPORT_HEADER_METADATA)
    writer.writerows(get_queries_report_rows(logs, include_content=can_view_content))
    return response
