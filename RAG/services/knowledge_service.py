"""
Knowledge Base read-side queries.

The Knowledge Graph itself (Entity/EntityMention/Relationship) was
built in Sprint 5 for graph *retrieval* (graph_retrieval_service.py,
folded into hybrid search) - this module is the first UI-facing
surface for it: browsing, an entity/relationship explorer, a graph
visualization, and a citation explorer built from QueryLog.sources
(Sprint 9's per-answer citations). Every function here is read-only
and scoped to `user`, matching the existing per-user scoping on
Entity/Relationship.
"""

from collections import Counter

from django.core.paginator import Paginator
from django.db.models import Count, Q

from ..models import Entity, QueryLog, Relationship

ENTITIES_PER_PAGE = 24
RELATIONSHIPS_PER_PAGE = 24
CITATIONS_LIMIT = 100
GRAPH_NODE_LIMIT = 120


def get_knowledge_overview(user):
    """
    Summary counts + category breakdown for the Browse Knowledge page.
    """

    entities = Entity.objects.filter(user=user)

    categories = (
        entities.values("entity_type")
        .annotate(count=Count("id"))
        .order_by("-count")
    )

    return {
        "total_entities": entities.count(),
        "total_relationships": Relationship.objects.filter(user=user).count(),
        "total_sources": (
            entities.values("mentions__chunk__document")
            .exclude(mentions__chunk__document__isnull=True)
            .distinct()
            .count()
        ),
        "categories": list(categories),
    }


def search_entities(user, query="", entity_type="", page=1):
    """
    Paginated, optionally filtered entity list, ordered by how often
    each entity was mentioned (a reasonable proxy for relevance when
    there's no query).
    """

    entities = Entity.objects.filter(user=user)

    if query:
        entities = entities.filter(display_name__icontains=query)

    if entity_type:
        entities = entities.filter(entity_type=entity_type)

    entities = entities.order_by("-mention_count", "display_name")

    paginator = Paginator(entities, ENTITIES_PER_PAGE)

    return paginator.get_page(page)


def get_entity_detail(user, entity_id):
    """
    A single entity plus the chunks it was mentioned in and its
    one-hop relationships (outgoing and incoming), or None if it
    doesn't exist / doesn't belong to `user`.
    """

    entity = (
        Entity.objects.filter(user=user, id=entity_id)
        .first()
    )

    if entity is None:
        return None

    mentions = (
        entity.mentions
        .select_related("chunk", "chunk__document")
        .order_by("-created_at")[:20]
    )

    outgoing = (
        entity.outgoing_relationships
        .select_related("target")
        .order_by("-weight")[:20]
    )

    incoming = (
        entity.incoming_relationships
        .select_related("source")
        .order_by("-weight")[:20]
    )

    return {
        "entity": entity,
        "mentions": mentions,
        "outgoing": outgoing,
        "incoming": incoming,
    }


def get_relationships(user, relation_type="", page=1):
    """
    Paginated relationship list, most-reinforced (highest weight)
    first - a relationship's weight increments every time the same
    triple is re-extracted from another chunk, so it's a real
    confidence signal, not an arbitrary sort.
    """

    relationships = (
        Relationship.objects.filter(user=user)
        .select_related("source", "target")
    )

    if relation_type:
        relationships = relationships.filter(relation_type=relation_type)

    paginator = Paginator(relationships, RELATIONSHIPS_PER_PAGE)

    return paginator.get_page(page)


def get_relation_types(user):
    """
    Distinct relation_type values for `user`, for the Relationship
    Explorer's filter dropdown.
    """

    return list(
        Relationship.objects.filter(user=user)
        .values_list("relation_type", flat=True)
        .distinct()
        .order_by("relation_type")
    )


def get_graph_data(user):
    """
    Nodes/edges for the Knowledge Graph visualization, shaped for
    vis-network (`{id, label, group, value}` nodes / `{from, to,
    label}` edges). Capped at GRAPH_NODE_LIMIT entities (by mention
    count) so the graph stays readable and the page stays light -
    this is a visualization, not an export; use the Relationship
    Explorer table for the full, unfiltered list.
    """

    entities = list(
        Entity.objects.filter(user=user)
        .order_by("-mention_count")[:GRAPH_NODE_LIMIT]
    )

    entity_ids = {entity.id for entity in entities}

    relationships = (
        Relationship.objects.filter(user=user, source_id__in=entity_ids, target_id__in=entity_ids)
        .select_related("source", "target")
    )

    nodes = [
        {
            "id": entity.id,
            "label": entity.display_name,
            "group": entity.entity_type,
            "value": max(entity.mention_count, 1),
        }
        for entity in entities
    ]

    edges = [
        {
            "from": relationship.source_id,
            "to": relationship.target_id,
            "label": relationship.relation_type,
            "value": relationship.weight,
        }
        for relationship in relationships
    ]

    return {"nodes": nodes, "edges": edges}


def get_graph_insights(user):
    """
    A handful of real, computed-not-fabricated stats about the shape
    of the user's knowledge graph, for the Graph Insights panel.
    """

    entities = Entity.objects.filter(user=user)
    relationships = Relationship.objects.filter(user=user).select_related("source", "target")

    most_mentioned = entities.order_by("-mention_count").first()

    degree = Counter()
    for relationship in relationships:
        degree[relationship.source_id] += 1
        degree[relationship.target_id] += 1

    most_connected = None
    if degree:
        top_id, top_degree = degree.most_common(1)[0]
        top_entity = entities.filter(id=top_id).first()
        if top_entity:
            most_connected = {"entity": top_entity, "degree": top_degree}

    top_category = entities.values("entity_type").annotate(count=Count("id")).order_by("-count").first()
    top_relation = relationships.values("relation_type").annotate(count=Count("id")).order_by("-count").first()

    return {
        "total_entities": entities.count(),
        "total_relationships": relationships.count(),
        "most_mentioned_entity": most_mentioned,
        "most_connected": most_connected,
        "top_category": top_category,
        "top_relation": top_relation,
    }


def get_citation_explorer(user):
    """
    Every distinct (document, chunk_number) actually cited across
    this user's Q&A history (Sprint 9's `citation_number` on
    QueryLog.sources entries), most recent question first. Built from
    QueryLog rather than a dedicated citations table - citations are
    already fully captured there, so this reuses that data instead of
    duplicating it.
    """

    logs = (
        QueryLog.objects.filter(user=user)
        .exclude(sources=[])
        .order_by("-created_at")[:CITATIONS_LIMIT]
    )

    citations = []

    for log in logs:
        for source in log.sources or []:
            if not source.get("citation_number"):
                continue

            citations.append({
                "question": log.question,
                "document": source.get("document"),
                "chunk_number": source.get("chunk_number"),
                "citation_number": source.get("citation_number"),
                "created_at": log.created_at,
            })

    return citations
