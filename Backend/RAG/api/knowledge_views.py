"""
Knowledge Center endpoints for the React SPA - thin JSON wrappers
around RAG/services/knowledge_service.py, the exact same read-only,
accessible-document-scoped queries RAG/views.py's knowledge_base_view/
entity_detail_view/relationships_view/knowledge_graph_view/
graph_node_detail_json/graph_edge_detail_json/citation_explorer_view/
knowledge_insights_view/document_knowledge_view already run. No new
business logic - only serialization of the model instances those
functions return (Entity/Relationship/Document/EntityMention) into
plain JSON, since knowledge_service already returns plain dicts for
the parts of its output that don't need serializing (Topics).
"""

from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from ..models import Document
from ..services import knowledge_service as ks
from ..services.document_access_service import get_accessible_document_ids
from ..utils.formatting import format_bytes
from .permissions import HasPagePermission

_kb_permission = permission_classes([HasPagePermission("pages.knowledge_base")])


def _entity(e, **extra):
    if e is None:
        return None
    return {
        "id": e.id,
        "display_name": e.display_name,
        "entity_type": e.entity_type,
        "color": ks.get_entity_type_color(e.entity_type),
        "mention_count": e.mention_count,
        **extra,
    }


def _doc(d, **extra):
    if d is None:
        return None
    return {
        "id": d.id,
        "title": d.title,
        "file_type": d.file_type,
        "file_size": d.file_size,
        "file_size_display": format_bytes(d.file_size),
        "uploaded_at": d.uploaded_at,
        "category": d.category.name if getattr(d, "category_id", None) else None,
        "tags": [t.name for t in d.tags.all()] if hasattr(d, "tags") else [],
        "detail_url": f"/knowledge/documents/{d.id}/",
        **extra,
    }


def _rel(r, **extra):
    return {
        "id": r.id,
        "source": _entity(r.source),
        "target": _entity(r.target),
        "relation_type": r.relation_type,
        "weight": r.weight,
        "context": r.context,
        "created_at": r.created_at,
        "updated_at": r.updated_at,
        **extra,
    }


def _paginate(page_obj):
    return {
        "page": page_obj.number,
        "num_pages": page_obj.paginator.num_pages,
        "count": page_obj.paginator.count,
        "has_previous": page_obj.has_previous(),
        "has_next": page_obj.has_next(),
    }


def _recently_updated(events):
    out = []
    for e in events:
        if e["kind"] == "mention":
            out.append({"kind": "mention", "at": e["at"], "entity": _entity(e["entity"]), "document": _doc(e["document"]) if "document" in e else None})
        else:
            out.append({"kind": "relationship", "at": e["at"], "relationship": _rel(e["relationship"])})
    return out


@api_view(["GET"])
@_kb_permission
def knowledge_browse_view(request):
    dataset = ks._build_topic_dataset(request.user)
    overview = ks.get_knowledge_overview(request.user, dataset=dataset)
    insights = ks.get_knowledge_insights(request.user, dataset=dataset)

    query = request.GET.get("q", "").strip()
    entity_type = request.GET.get("type", "").strip()
    topics_page = ks.search_topics(request.user, query=query, entity_type=entity_type, page=request.GET.get("page"), dataset=dataset)

    return Response({
        "overview": overview,
        "recently_updated": _recently_updated(insights["recently_updated"][:6]),
        "topics": list(topics_page),
        "pagination": _paginate(topics_page),
        "query": query,
        "selected_type": entity_type,
    })


@api_view(["GET"])
@_kb_permission
def entity_detail_view(request, entity_id):
    detail = ks.get_topic_detail(request.user, entity_id)
    if detail is None:
        raise Http404

    return Response({
        "entity": _entity(detail["entity"]),
        "member_count": detail["member_count"],
        "mention_count": detail["mention_count"],
        "document_count": detail["document_count"],
        "document_buckets": [
            {"label": label, "documents": [_doc(d) for d in docs]}
            for label, docs in detail["document_buckets"]
        ],
        "related_teams": [_entity(e) for e in detail["related_teams"]],
        "outgoing": [_rel(r) for r in detail["outgoing"]],
        "incoming": [_rel(r) for r in detail["incoming"]],
        "cross_reference_documents": [_doc(d) for d in detail["cross_reference_documents"]],
        "timeline": detail["timeline"],
        "citations": detail["citations"],
        "mentions": [
            {
                "id": m.id,
                "document": m.chunk.document.title,
                "document_id": m.chunk.document_id,
                "chunk_number": m.chunk.chunk_number,
                "created_at": m.created_at,
            }
            for m in detail["mentions"]
        ],
    })


@api_view(["GET"])
@_kb_permission
def relationships_view(request):
    relation_type = request.GET.get("type", "").strip()
    page_obj = ks.get_relationships(request.user, relation_type=relation_type, page=request.GET.get("page"))

    return Response({
        "relationships": [_rel(r) for r in page_obj],
        "pagination": _paginate(page_obj),
        "relation_types": ks.get_relation_types(request.user),
        "selected_type": relation_type,
    })


@api_view(["GET"])
@_kb_permission
def knowledge_graph_view(request):
    graph_data = ks.get_graph_data(request.user)
    insights = ks.get_graph_insights(request.user)

    present_types = sorted({node["group"] for node in graph_data["nodes"]})
    entity_type_colors = {t: ks.get_entity_type_color(t) for t in present_types}

    return Response({
        "graph_data": graph_data,
        "insights": {
            "total_entities": insights["total_entities"],
            "total_relationships": insights["total_relationships"],
            "most_mentioned_entity": insights["most_mentioned_entity"],
            "most_connected": insights["most_connected"],
            "top_category": insights["top_category"],
            "top_relation": insights["top_relation"],
        },
        "entity_type_colors": entity_type_colors,
    })


@api_view(["GET"])
@_kb_permission
def graph_node_detail_view(request, entity_id):
    detail = ks.get_topic_node_detail(request.user, entity_id)
    if detail is None:
        raise Http404
    return Response(detail)


@api_view(["GET"])
@_kb_permission
def graph_edge_detail_view(request):
    try:
        topic_a_id = int(request.GET.get("a"))
        topic_b_id = int(request.GET.get("b"))
    except (TypeError, ValueError):
        return Response({"error": "Query params 'a' and 'b' must be entity ids."}, status=400)

    detail = ks.get_topic_pair_relationship_detail(request.user, topic_a_id, topic_b_id)
    if detail is None:
        raise Http404
    return Response(detail)


@api_view(["GET"])
@_kb_permission
def citation_explorer_view(request):
    citations = ks.resolve_topics_for_citations(request.user, ks.get_citation_explorer(request.user))
    return Response({"citations": citations})


@api_view(["GET"])
@_kb_permission
def knowledge_insights_view(request):
    insights = ks.get_knowledge_insights(request.user)

    return Response({
        "most_referenced_documents": [_doc(d, mention_total=d.mention_total) for d in insights["most_referenced_documents"]],
        "frequently_connected_topics": insights["frequently_connected_topics"],
        "recently_updated": _recently_updated(insights["recently_updated"]),
        "not_processed": [_doc(d) for d in insights["not_processed"]],
        "processed_without_extraction": [_doc(d) for d in insights["processed_without_extraction"]],
        "weak_topics": insights["weak_topics"],
        "duplicate_clusters": [
            {"documents": [_doc(d) for d in cluster["documents"]]} for cluster in insights["duplicate_clusters"]
        ],
        "total_accessible_documents": insights["total_accessible_documents"],
        "total_topics": insights["total_topics"],
    })


@api_view(["GET"])
@_kb_permission
def document_knowledge_view(request, doc_id):
    document = get_object_or_404(Document, id=doc_id, id__in=get_accessible_document_ids(request.user))

    knowledge = ks.get_document_knowledge(request.user, document)
    if knowledge is None:
        raise Http404

    is_owner = document.user_id == request.user.id

    return Response({
        "document": _doc(
            document,
            chunk_count=document.chunk_count,
            processing_status=document.processing_status,
            is_org_library=document.is_org_library,
            collections=[m.collection.name for m in document.collection_memberships.select_related("collection").all()],
        ),
        "is_owner": is_owner,
        "topics": knowledge["topics"],
        "relationships": [_rel(r) for r in knowledge["relationships"]],
        "related_by_topic": [
            {"document": _doc(row["document"]), "shared_topics": row["shared_topics"]}
            for row in knowledge["related_by_topic"]
        ],
        "similar_documents": [
            {"document": _doc(row["document"]), "similarity": row["similarity"]}
            for row in knowledge["similar_documents"]
        ],
        "citations": knowledge["citations"],
        "shares": (
            [
                {
                    "id": s.id,
                    "shared_with_user": s.shared_with_user.username if s.shared_with_user_id else None,
                    "shared_with_role": s.shared_with_role.name if s.shared_with_role_id else None,
                    "invited_email": s.invited_email,
                }
                for s in document.shares.select_related("shared_with_user", "shared_with_role")
            ]
            if is_owner else None
        ),
    })
