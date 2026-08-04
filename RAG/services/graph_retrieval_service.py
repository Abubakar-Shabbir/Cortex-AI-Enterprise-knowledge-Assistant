"""
Graph-based retrieval.

Matches entities mentioned in a question against the user's knowledge
graph, expands one relationship hop, and returns the chunks that
support those entities. Results use the same shape as
vector_search()/bm25_search() ("content", "document", "chunk_number",
"score", "search_type") so retrieval_service can merge all three
sources directly.
"""

import logging

from django.db.models import Q

from ..models import Entity, EntityMention, Relationship
from .retrieval_filters import apply_document_filters

logger = logging.getLogger(__name__)

MAX_MATCHED_ENTITIES = 5
MAX_RELATIONSHIP_EDGES = 20


def _match_entities(question: str, user):
    """
    Lightweight lexical match: which of the user's known entities are
    mentioned in the question. Mirrors bm25_service's in-Python
    scoring approach rather than running a second LLM extraction at
    query time, keeping graph lookups fast and free of extra API cost.
    """

    question_lower = question.lower()

    matched = [
        entity
        for entity in Entity.objects.filter(user=user).only(
            "id", "name", "display_name", "entity_type", "mention_count"
        )
        if entity.name and entity.name in question_lower
    ]

    matched.sort(key=lambda entity: len(entity.name), reverse=True)

    return matched[:MAX_MATCHED_ENTITIES]


def _expand_neighbors(matched_entities, user):
    """
    One-hop expansion: add entities directly connected to a matched
    entity via a Relationship edge, so retrieval also surfaces chunks
    about closely related entities, not just literal name matches.
    """

    entities_by_id = {entity.pk: entity for entity in matched_entities}

    if not entities_by_id:
        return list(entities_by_id.values())

    edges = (
        Relationship.objects.filter(user=user)
        .filter(Q(source_id__in=entities_by_id) | Q(target_id__in=entities_by_id))
        .select_related("source", "target")
        .order_by("-weight")[:MAX_RELATIONSHIP_EDGES]
    )

    for edge in edges:
        entities_by_id.setdefault(edge.source_id, edge.source)
        entities_by_id.setdefault(edge.target_id, edge.target)

    return list(entities_by_id.values())


def graph_search(question: str, user, top_k: int, filters=None):
    """
    Retrieve chunks connected to the question's entities via the
    knowledge graph.

    Returns [] when there's no user (anonymous callers keep the
    existing vector+BM25-only behavior) or no entities matched -
    this is intentionally a pure addition to retrieval, never a
    replacement.
    """

    if user is None:
        return []

    try:
        matched = _match_entities(question, user)

        if not matched:
            return []

        expanded = _expand_neighbors(matched, user)

        mentions_queryset = (
            EntityMention.objects.filter(entity__in=expanded)
            .select_related("chunk", "chunk__document", "entity")
        )

        mentions_queryset = apply_document_filters(
            mentions_queryset, filters, document_field="chunk__document"
        )

        mentions = mentions_queryset.order_by("-entity__mention_count")[: top_k * 2]

        results = []
        seen = set()

        for mention in mentions:

            chunk = mention.chunk
            key = (chunk.document.title, chunk.chunk_number)

            if key in seen:
                continue

            seen.add(key)

            results.append(
                {
                    "content": chunk.content,
                    "document": chunk.document.title,
                    "chunk_number": chunk.chunk_number,
                    "score": mention.entity.mention_count,
                    "search_type": "graph",
                }
            )

            if len(results) >= top_k:
                break

        return results

    except Exception:
        logger.exception("Graph retrieval failed for question: %r", question)
        return []
