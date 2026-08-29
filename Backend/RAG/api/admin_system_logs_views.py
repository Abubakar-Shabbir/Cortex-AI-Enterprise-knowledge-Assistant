"""
Admin > System Logs endpoints for the React SPA - thin JSON wrappers
around RAG.views.admin_system_logs_view/admin_trace_detail_view/
admin_error_group_detail_view's exact same service calls
(observability_service.py, error_intelligence_service.py,
RAG.views._build_activity_events). Same three-tab scoping (each gated
by its own permission) and same location-data scrubbing rule.
"""

from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import BasePermission
from rest_framework.response import Response

from .. import views as classic_views
from ..models import AIRequestTrace, AITaskRun, ErrorGroup
from ..services import error_intelligence_service, observability_service
from ..services.permission_service import has_any_system_logs_permission, user_has_permission
from .permissions import HasPagePermission


class _HasAnySystemLogsPermission(BasePermission):
    """Mirrors RAG.decorators.system_logs_access_required - at least one of SYSTEM_LOGS_PERMISSIONS, not all (unlike HasPagePermission)."""

    message = "You don't have access to this resource."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and has_any_system_logs_permission(request.user))


def _serialize_trace(t):
    return {
        "trace_id": t.trace_id,
        "source_display": t.get_source_display(),
        "user": t.user.username if t.user else None,
        "status": t.status,
        "status_display": t.get_status_display(),
        "provider": t.provider,
        "model": t.model,
        "providers_attempted": t.providers_attempted,
        "total_duration_ms": t.total_duration_ms,
        "bottleneck_label": t.bottleneck_label,
        "total_tokens": t.total_tokens,
        "created_at": t.created_at,
    }


def _serialize_error_group(g):
    return {
        "id": g.id,
        "logger_name": g.logger_name,
        "level": g.level,
        "severity": g.severity,
        "message": g.message,
        "occurrence_count": g.occurrence_count,
        "first_seen": g.first_seen,
        "last_seen": g.last_seen,
    }


def _serialize_run(run):
    return {
        "id": run.id,
        "status": run.status,
        "status_display": run.get_status_display(),
        "task_type_display": run.get_task_type_display(),
        "username": run.user.username if run.user_id else None,
        "document_count": run.document_count,
        "created_at": run.created_at,
        "stuck_pending": run.status == AITaskRun.Status.PENDING and (timezone.now() - run.created_at) > timedelta(minutes=2),
    }


@api_view(["GET"])
@permission_classes([HasPagePermission("system.view_ai_logs")])
def admin_trace_detail_view(request, trace_id):
    trace = AIRequestTrace.objects.select_related("user").filter(trace_id=trace_id).first()
    if trace is None:
        return Response({"error": "Not found."}, status=404)

    bottleneck_members = observability_service.STAGE_GROUPS.get(trace.bottleneck_stage, set())
    llm_stage_members = observability_service.STAGE_GROUPS.get("LLM Generation", set())
    had_fallback_or_retry = trace.retry_count > 0 or len(trace.providers_attempted or []) > 1

    stages = []
    for stage in (trace.stages or []):
        tags = []
        if trace.bottleneck_stage and stage["name"] in bottleneck_members:
            tags.append("bottleneck")
        if had_fallback_or_retry and stage["name"] in llm_stage_members:
            tags.append("retry")
        stages.append({**stage, "tags": tags})

    return Response({
        "trace_id": trace.trace_id,
        "source": trace.get_source_display(),
        "status": trace.status,
        "user": trace.user.username if trace.user else None,
        "provider": trace.provider,
        "model": trace.model,
        "providers_attempted": trace.providers_attempted,
        "retry_count": trace.retry_count,
        "prompt_tokens": trace.prompt_tokens,
        "completion_tokens": trace.completion_tokens,
        "total_tokens": trace.total_tokens,
        "llm_latency_ms": trace.llm_latency_ms,
        "time_to_first_token_ms": trace.time_to_first_token_ms,
        "retrieved_chunks": trace.retrieved_chunks,
        "citation_count": trace.citation_count,
        "cache_hit": trace.cache_hit,
        "stages": stages,
        "total_duration_ms": trace.total_duration_ms,
        "bottleneck_label": trace.bottleneck_label,
        "error_type": trace.error_type,
        "error_message": trace.error_message,
        "created_at": trace.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        "query_log_id": trace.query_log_id,
        "ai_task_run_id": trace.ai_task_run_id,
    })


@api_view(["GET"])
@permission_classes([HasPagePermission("system.view_ai_logs")])
def admin_error_group_detail_view(request, group_id):
    group = ErrorGroup.objects.filter(id=group_id).first()
    if group is None:
        return Response({"error": "Not found."}, status=404)

    occurrence_trace_ids = [o["trace_id"] for o in (group.recent_occurrences or []) if o.get("trace_id")]
    existing_trace_ids = set(AIRequestTrace.objects.filter(trace_id__in=occurrence_trace_ids).values_list("trace_id", flat=True))

    occurrences = [
        {"trace_id": o.get("trace_id"), "timestamp": o.get("timestamp"), "trace_exists": o.get("trace_id") in existing_trace_ids}
        for o in reversed(group.recent_occurrences or [])
    ]

    return Response({
        "id": group.id,
        "logger_name": group.logger_name,
        "level": group.level,
        "error_type": group.error_type,
        "message": group.message,
        "occurrence_count": group.occurrence_count,
        "severity": group.severity,
        "first_seen": group.first_seen.strftime("%Y-%m-%d %H:%M:%S"),
        "last_seen": group.last_seen.strftime("%Y-%m-%d %H:%M:%S"),
        "occurrences": occurrences,
    })


@api_view(["GET"])
@permission_classes([_HasAnySystemLogsPermission])
def admin_system_logs_view(request):
    can_view_traces = user_has_permission(request.user, "system.view_ai_logs")
    can_view_activity = user_has_permission(request.user, "activity.view_all_logs")
    can_view_activity_location = can_view_activity and user_has_permission(request.user, "activity.view_ip_location")

    payload = {
        "can_view_traces": can_view_traces,
        "can_view_activity": can_view_activity,
        "can_view_activity_location": can_view_activity_location,
    }

    if can_view_traces:
        filters = {k: request.query_params.get(k, "") for k in ("source", "provider", "model", "status", "error_type", "date_from", "date_to", "trace_id")}
        try:
            page = max(1, int(request.query_params.get("page", 1)))
        except ValueError:
            page = 1

        listing = observability_service.list_traces(filters, page_size=25, page=page)
        summary = AIRequestTrace.objects.aggregate(
            total=Count("id"), failed=Count("id", filter=Q(status=AIRequestTrace.Status.FAILED)),
            ask_ai=Count("id", filter=Q(source=AIRequestTrace.Source.ASK_AI)),
            ai_task=Count("id", filter=Q(source=AIRequestTrace.Source.AI_TASK)),
        )

        active_ai_task_runs = list(
            AITaskRun.objects.filter(status__in=[AITaskRun.Status.PENDING, AITaskRun.Status.RUNNING]).select_related("user").order_by("created_at")[:50]
        )

        eg_filters = {
            "logger_name": request.query_params.get("eg_logger", ""), "level": request.query_params.get("eg_level", ""),
            "q": request.query_params.get("eg_q", ""), "date_from": request.query_params.get("eg_date_from", ""),
            "date_to": request.query_params.get("eg_date_to", ""),
        }
        try:
            eg_page = max(1, int(request.query_params.get("eg_page", 1)))
        except ValueError:
            eg_page = 1
        eg_listing = error_intelligence_service.list_error_groups(eg_filters, page_size=25, page=eg_page)

        payload.update({
            "traces": [_serialize_trace(t) for t in listing["results"]],
            "total": listing["total"], "page": listing["page"], "num_pages": listing["num_pages"],
            "filter_options": observability_service.get_filter_options(),
            "summary": summary,
            "active_ai_task_runs": [_serialize_run(r) for r in active_ai_task_runs],
            "error_groups": [_serialize_error_group(g) for g in eg_listing["results"]],
            "eg_total": eg_listing["total"], "eg_page": eg_listing["page"], "eg_num_pages": eg_listing["num_pages"],
        })

    if can_view_activity:
        act_filters = {
            "type": request.query_params.get("act_type", ""), "actor": request.query_params.get("act_actor", ""),
            "q": request.query_params.get("act_q", ""), "location": request.query_params.get("act_location", ""),
            "date_from": request.query_params.get("act_date_from", ""), "date_to": request.query_params.get("act_date_to", ""),
        }
        try:
            act_page = max(1, int(request.query_params.get("act_page", 1)))
        except ValueError:
            act_page = 1
        if not can_view_activity_location:
            act_filters["location"] = ""

        from django.core.paginator import Paginator
        activity_events = classic_views._build_activity_events(act_filters, include_location=can_view_activity_location)
        act_paginator = Paginator(activity_events, 25)
        act_page_obj = act_paginator.get_page(act_page)

        from ..models import ActivityLog
        activity_types = ["document.uploaded"] + list(ActivityLog.objects.order_by().values_list("action", flat=True).distinct())

        act_summary = {"total_events": ActivityLog.objects.count()}
        if can_view_activity_location:
            act_summary["tracked_ips"] = ActivityLog.objects.exclude(ip_address__isnull=True).values("ip_address").distinct().count()
            act_summary["countries"] = ActivityLog.objects.exclude(country="").values("country").distinct().count()
        act_summary["security_alerts"] = ActivityLog.objects.filter(action="security.privilege_escalation_blocked").count()

        payload.update({
            "activity_results": list(act_page_obj),
            "act_page": act_page_obj.number, "act_num_pages": act_paginator.num_pages, "act_total": len(activity_events),
            "act_has_previous": act_page_obj.has_previous(), "act_has_next": act_page_obj.has_next(),
            "activity_types": sorted(set(activity_types)),
            "act_summary": act_summary,
        })

    requested_tab = request.query_params.get("tab", "")
    if requested_tab in ("traces", "errors", "activity"):
        default_tab = requested_tab
    elif can_view_traces:
        default_tab = "traces"
    else:
        default_tab = "activity"
    payload["default_tab"] = default_tab

    return Response(payload)
