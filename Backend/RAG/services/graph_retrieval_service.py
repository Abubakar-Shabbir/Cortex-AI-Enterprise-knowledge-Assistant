"""
Graph-based retrieval.

Matches entities mentioned in a question against the user's knowledge
graph, expands one relationship hop, and returns the chunks that
support those entities. Results use the same shape as
vector_search()/bm25_search() ("content", "document", "chunk_number",
"score", "search_type") so retrieval_service can merge all three
sources directly.
"""

import hashlib
import logging

from django.conf import settings
from django.core.cache import cache
from django.db.models import Q

from ..models import Entity, EntityMention, Relationship
from .document_access_service import get_accessible_document_ids
from .perf import timed_stage
from .retrieval_filters import apply_document_filters

logger = logging.getLogger(__name__)

MAX_MATCHED_ENTITIES = 5
MAX_RELATIONSHIP_EDGES = 20


def _entity_scope_cache_key(accessible_document_ids):
    """Fingerprints the viewer's accessible scope + how many entity mentions currently exist within it - same self-invalidating pattern as bm25_service._bm25_cache_key."""

    ids_fingerprint = hashlib.sha256(
        ",".join(str(i) for i in sorted(accessible_document_ids)).encode()
    ).hexdigest()
    mention_count = EntityMention.objects.filter(chunk__document_id__in=accessible_document_ids).count()

    return f"graph_visible_entities:{ids_fingerprint}:{mention_count}"


def _visible_entities(accessible_document_ids):
    """
    Every Entity with at least one mention in an accessible document -
    the expensive, full-corpus-scan part of _match_entities() below,
    cached per accessible-scope for settings.RETRIEVAL_CACHE_TTL
    seconds. Previously this reloaded on every single question
    regardless of whether the graph had changed at all.
    """

    cache_key = _entity_scope_cache_key(accessible_document_ids)
    cached = cache.get(cache_key)

    if cached is not None:
        return cached

    with timed_stage("graph entity scope build (cache miss)", accessible_docs=len(accessible_document_ids)):

        entity_ids = (
            EntityMention.objects.filter(chunk__document_id__in=accessible_document_ids)
            .values_list("entity_id", flat=True)
            .distinct()
        )

        entities = list(
            Entity.objects.filter(id__in=entity_ids).only(
                "id", "name", "display_name", "entity_type", "mention_count"
            )
        )

    cache.set(cache_key, entities, settings.RETRIEVAL_CACHE_TTL)

    return entities


def _match_entities(question: str, accessible_document_ids):
    """
    Lightweight lexical match: which entities mentioned in `question`
    have at least one mention in a document the viewer can access
    (owned + Organization Library + shared-with-them - see
    document_access_service). Entity.user is always the document's
    *uploader*, not the viewer, so a shared/org document's entities
    belong to someone else's Entity rows - matching by accessible
    document rather than by Entity.user is what makes them visible to
    a sharee at all. Mirrors bm25_service's in-Python scoring approach
    rather than running a second LLM extraction at query time, keeping
    graph lookups fast and free of extra API cost.
    """

    question_lower = question.lower()

    matched = [
        entity
        for entity in _visible_entities(accessible_document_ids)
        if entity.name and entity.name in question_lower
    ]

    matched.sort(key=lambda entity: len(entity.name), reverse=True)

    return matched[:MAX_MATCHED_ENTITIES]


def _expand_neighbors(matched_entities, accessible_document_ids):
    """
    One-hop expansion: add entities directly connected to a matched
    entity via a Relationship edge, so retrieval also surfaces chunks
    about closely related entities, not just literal name matches.

    Traverses every Relationship edge regardless of who extracted it
    (an edge from a document the viewer can't see may still connect
    two entities that ARE independently visible to them), but only
    ever admits a *newly discovered* neighbor entity if it has a
    mention in a document the viewer can access - this is what stops
    an edge from leaking a neighbor that lives only in an inaccessible
    document. The final chunk results are also independently filtered
    to accessible documents by graph_search() below, so this gate is
    defense-in-depth on relevance, not the only thing standing between
    a viewer and private chunk content.
    """

    entities_by_id = {entity.pk: entity for entity in matched_entities}

    if not entities_by_id:
        return list(entities_by_id.values())

    edges = list(
        Relationship.objects.filter(Q(source_id__in=entities_by_id) | Q(target_id__in=entities_by_id))
        .select_related("source", "target")
        .order_by("-weight")[:MAX_RELATIONSHIP_EDGES]
    )

    candidate_ids = {
        entity_id
        for edge in edges
        for entity_id in (edge.source_id, edge.target_id)
        if entity_id not in entities_by_id
    }

    accessible_entity_ids = set()
    if candidate_ids:
        accessible_entity_ids = set(
            EntityMention.objects.filter(
                entity_id__in=candidate_ids, chunk__document_id__in=accessible_document_ids
            ).values_list("entity_id", flat=True).distinct()
        )

    for edge in edges:
        if edge.source_id in entities_by_id or edge.source_id in accessible_entity_ids:
            entities_by_id.setdefault(edge.source_id, edge.source)
        if edge.target_id in entities_by_id or edge.target_id in accessible_entity_ids:
            entities_by_id.setdefault(edge.target_id, edge.target)

    return list(entities_by_id.values())


def graph_search(question: str, user, top_k: int, filters=None, accessible_document_ids=None):
    """
    Retrieve chunks connected to the question's entities via the
    knowledge graph, scoped to `user`'s full accessible document set
    (owned + Organization Library + shared-with-them).

    Returns [] when there's no user (anonymous callers keep the
    existing vector+BM25-only behavior), no accessible documents, or
    no entities matched - this is intentionally a pure addition to
    retrieval, never a replacement.

    `accessible_document_ids`, when provided, is used as-is instead of
    recomputing it here - lets retrieve_chunks() compute it once and
    share it across vector/BM25/graph search.
    """

    if user is None:
        return []

    try:
        if accessible_document_ids is None:
            accessible_document_ids = get_accessible_document_ids(user)

        if not accessible_document_ids:
            return []

        matched = _match_entities(question, accessible_document_ids)

        if not matched:
            return []

        expanded = _expand_neighbors(matched, accessible_document_ids)

        mentions_queryset = (
            EntityMention.objects.filter(entity__in=expanded, chunk__document_id__in=accessible_document_ids)
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
