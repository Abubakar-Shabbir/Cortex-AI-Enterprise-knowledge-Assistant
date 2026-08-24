"""
Ask AI (AI Search) as JSON/SSE - reuses the exact same service calls
RAG.views.ask_ai/ask_ai_stream already make (answer_question(),
answer_question_stream(), RetrievalFilters.from_request()). Unlike the
classic ask_ai_stream view, the "done" SSE event here carries the
structured result as JSON rather than a server-rendered HTML partial -
React renders its own result card from that data (AskResult.jsx),
mirroring partials/_ask_ai_result.html's markup instead of swapping in
server HTML, since a React view must own its own DOM.
"""

import json
import logging

from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import AIRequestTrace, Entity, QueryLog
from ..services.citation_service import render_answer_html
from ..services.categories_service import list_categories
from ..services.collections_service import list_collections
from ..services.document_access_service import get_accessible_documents
from ..services.prompt_templates import is_not_found_answer, is_service_unavailable_answer
from ..services.query_service import answer_question, answer_question_stream
from ..services.knowledge_service import get_related_topics_for_citations
from ..services.retrieval_filters import RetrievalFilters
from ..services.tags_service import list_tags
from ..services.trace import bind_trace_id
from .permissions import HasPagePermission

logger = logging.getLogger(__name__)


def _serialize_topics(related_topics):
    """related_topics is a list of Entity model instances (see query_service.py) except when a caller (ask_log_detail_view) has already reduced it to plain dicts - handle both so this stays the single place that shapes it for JSON."""

    return [
        topic if isinstance(topic, dict) else {"id": topic.id, "name": topic.name}
        for topic in related_topics
    ]


def _decorate_result(result):
    result["answer_html"] = render_answer_html(result["answer"])
    result["is_service_unavailable"] = is_service_unavailable_answer(result["answer"])
    result["is_not_found"] = is_not_found_answer(result["answer"]) and not result["is_service_unavailable"]
    result["related_topics"] = _serialize_topics(result.get("related_topics") or [])
    return result


def _filters_from_payload(data):
    return RetrievalFilters.from_request(
        document_ids=data.get("document_ids") or [],
        file_types=data.get("file_types") or [],
        uploaded_after=data.get("uploaded_after") or None,
        uploaded_before=data.get("uploaded_before") or None,
        collection_id=data.get("collection_id") or None,
        category_id=data.get("category_id") or None,
        tag_id=data.get("tag_id") or None,
        org_library_only=bool(data.get("org_library_only")),
    )


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.ask_ai")])
def ask_context_view(request):
    """Filter options + suggested/recent questions - everything ask_ai.html needs before the first question is asked."""

    user = request.user
    documents = get_accessible_documents(user).order_by("title")

    recent_questions = QueryLog.objects.filter(user=user).order_by("-created_at")[:6]

    suggested_questions = [
        f"What can you tell me about {entity.display_name}?"
        for entity in Entity.objects.filter(user=user).order_by("-mention_count")[:4]
    ]

    return Response({
        "documents": [{"id": d.id, "title": d.title} for d in documents],
        "collections": [{"id": c.id, "name": c.name} for c in list_collections(user)],
        "categories": [{"id": c.id, "name": c.name} for c in list_categories(user)],
        "tags": [{"id": t.id, "name": t.name} for t in list_tags(user)],
        "recent_questions": [
            {
                "id": log.id,
                "question": log.question,
                "confidence": log.confidence,
                "created_at": log.created_at.isoformat(),
            }
            for log in recent_questions
        ],
        "suggested_questions": suggested_questions,
        "allowed_file_extensions": [ext.lstrip(".") for ext in settings.ALLOWED_FILE_EXTENSIONS],
    })


@api_view(["GET"])
@permission_classes([HasPagePermission("pages.ask_ai")])
def ask_log_detail_view(request, log_id):
    """Replays an already-answered question from its QueryLog row - no retrieval, no LLM call, matches ask_ai()'s ?log_id= GET branch."""

    log = QueryLog.objects.filter(id=log_id, user=request.user).first()
    if not log:
        return Response({"error": "Not found."}, status=404)

    sources = log.sources or []
    citations = [source for source in sources if source.get("citation_number")]
    structured = log.structured_data or {}
    trace = AIRequestTrace.objects.filter(query_log=log).only("provider", "model", "providers_attempted").first()

    result = {
        "id": log.id,
        "question": log.question,
        "answer": log.answer,
        "sources": sources,
        "citations": citations,
        "response_time_ms": log.response_time_ms,
        "confidence": log.confidence,
        "search_method": log.search_method,
        "llm_provider": trace.provider if trace else "",
        "llm_model": trace.model if trace else "",
        "llm_fallback_used": bool(trace and len(trace.providers_attempted or []) > 1),
        "from_history": True,
        "key_points": structured.get("key_points", []),
        "table": structured.get("table"),
        "related_topics": get_related_topics_for_citations(request.user, citations),
    }

    return Response(_decorate_result(result))


@api_view(["POST"])
@permission_classes([HasPagePermission("pages.ask_ai")])
def ask_view(request):
    question = (request.data.get("question") or "").strip()
    if not question:
        return Response({"error": "A question is required."}, status=400)

    filters = _filters_from_payload(request.data)

    with bind_trace_id():
        result = answer_question(question, user=request.user, filters=filters)

    return Response(_decorate_result(result))


@api_view(["POST"])
@permission_classes([HasPagePermission("pages.ask_ai")])
def ask_stream_view(request):
    question = (request.data.get("question") or "").strip()
    if not question:
        return Response({"error": "A question is required."}, status=400)

    filters = _filters_from_payload(request.data)
    user = request.user

    def event_stream():
        with bind_trace_id() as trace_id:
            try:
                for event in answer_question_stream(question, user=user, filters=filters):
                    if event["type"] == "token":
                        yield f"data: {json.dumps({'type': 'token', 'text': event['text']})}\n\n"
                    elif event["type"] == "done":
                        result = _decorate_result(event["result"])
                        yield f"data: {json.dumps({'type': 'done', 'result': result})}\n\n"
            except Exception:
                logger.exception("[INFRA] ask_stream_view: streaming failed for question=%r trace_id=%s", question, trace_id)
                yield f"data: {json.dumps({'type': 'error', 'trace_id': trace_id})}\n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
