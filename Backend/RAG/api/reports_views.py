"""
Reports endpoints for the React SPA - thin JSON wrapper around
RAG.views.reports_view's exact same service calls, plus one plain
Django (non-DRF) view per CSV export, mirroring
RAG.views.export_documents_report/export_usage_report/
export_comparison_report/export_ai_task_runs_report/
export_knowledge_topics_report and ai_tasks_views.ai_task_export_view's
own streamed-CSV pattern. No new aggregation/row-building logic.
"""

import csv

from django.db.models import Sum
from django.http import HttpResponse, HttpResponseNotAllowed
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..decorators import permission_required
from ..models import AITaskRun, Document, QueryLog
from ..services.knowledge_service import get_knowledge_overview
from ..services.permission_service import user_has_permission
from ..services.reports_service import (
    AI_TASK_RUNS_REPORT_HEADER,
    COMPARISON_REPORT_HEADER,
    DOCUMENTS_REPORT_HEADER,
    KNOWLEDGE_TOPICS_REPORT_HEADER,
    USAGE_REPORT_HEADER,
    get_ai_task_runs_report_rows,
    get_comparison_report_rows,
    get_documents_report_rows,
    get_knowledge_topics_report_rows,
    get_usage_report_rows,
)
from ..services.stats_service import get_comparison_report_data, get_document_type_breakdown, get_kpi_trends
from ..utils.formatting import format_bytes
from .permissions import HasPagePermission


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.reports")])
def reports_view(request):
    documents = Document.objects.filter(user=request.user)

    return Response({
        "document_count": documents.count(),
        "total_storage": format_bytes(documents.aggregate(total=Sum("file_size"))["total"] or 0),
        "question_count": QueryLog.objects.filter(user=request.user).count(),
        "ai_task_run_count": AITaskRun.objects.filter(user=request.user).count(),
        "topic_count": get_knowledge_overview(request.user)["total_entities"],
        "comparison": get_comparison_report_data(request.user),
        "kpi_trends": get_kpi_trends(request.user),
        "document_types": get_document_type_breakdown(request.user),
        "can_view_ai_tasks": user_has_permission(request.user, "pages.ai_tasks"),
        "can_view_knowledge_base": user_has_permission(request.user, "pages.knowledge_base"),
    })


def _csv_response(filename, header, rows):
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    writer = csv.writer(response)
    writer.writerow(header)
    writer.writerows(rows)
    return response


@permission_required("pages.reports")
def export_documents_report_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return _csv_response("documents_report.csv", DOCUMENTS_REPORT_HEADER, get_documents_report_rows(request.user))


@permission_required("pages.reports")
def export_usage_report_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return _csv_response("usage_report.csv", USAGE_REPORT_HEADER, get_usage_report_rows(request.user))


@permission_required("pages.reports")
def export_comparison_report_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return _csv_response(
        "comparison_report.csv", COMPARISON_REPORT_HEADER,
        get_comparison_report_rows(get_comparison_report_data(request.user)),
    )


@permission_required("pages.reports")
def export_ai_task_runs_report_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return _csv_response("ai_task_runs_report.csv", AI_TASK_RUNS_REPORT_HEADER, get_ai_task_runs_report_rows(request.user))


@permission_required("pages.reports")
def export_knowledge_topics_report_view(request):
    if request.method != "GET":
        return HttpResponseNotAllowed(["GET"])
    return _csv_response("knowledge_topics_report.csv", KNOWLEDGE_TOPICS_REPORT_HEADER, get_knowledge_topics_report_rows(request.user))
