"""
Enterprise Knowledge Center read-side queries.

The Knowledge Graph itself (Entity/EntityMention/Relationship) was built
in Sprint 5 for graph *retrieval* (graph_retrieval_service.py, folded
into hybrid search); this module is the UI-facing surface for it -
Topic exploration, relationship/graph views, insights, and a citation
viewer built from QueryLog.sources. Every function here is read-only.

Scoping - the single most important rule in this file
-------------------------------------------------------
Entity/Relationship rows carry a `user` FK, but that's the document
*uploader*, not "who's allowed to see this." Every function below
resolves visibility the same way graph_retrieval_service.py already
does for Ask AI: via EntityMention -> chunk -> document against
document_access_service.get_accessible_document_ids(user) (owned union
Organization Library union shared-with-them/their-role). NEVER filter
by Entity.user/Relationship.user directly - that was the bug this
module used to have (a user with Org Library/shared access to a
document they didn't personally upload saw that document surface in
Ask AI answers, but nothing about it in the Knowledge Center - the
opposite of what an enterprise knowledge tool should do).

Topics - merging across uploaders without a schema change
-----------------------------------------------------------
Entity stays deduplicated per-uploader (`unique_together = ("user",
"name", "entity_type")`) - there's no Organization/tenant model in
this codebase to hang a real cross-user merge on, and adding one is
out of scope for "improve this module." Instead, every listing/detail
function groups the *visible* Entity rows in Python by their
`(name, entity_type)` key - `Entity.name` is already the normalized
dedup key computed by graph_service._get_or_create_entity(), so two
different users' rows for "steve jobs"/PERSON carry the exact same
`name` and group together for free, no extra normalization needed.
The result is a **Topic**: a plain dict (not a new model) aggregating
mention_count/entity_ids/document_count across every constituent
Entity, regardless of who uploaded the source document. A Topic's
"id" for URL purposes is its top (most-mentioned) constituent
Entity's id, so the existing /knowledge/entity/<id>/ route needs no
change - get_topic_detail() resolves the rest of the group from there.
"""

import logging
from collections import Counter, defaultdict

from django.core.paginator import Paginator
from django.db.models import Count
from django.urls import reverse

from ..models import Document, Entity, EntityMention, QueryLog, Relationship
from .ai_tasks_similarity_service import build_document_embedding, cluster_documents, cosine_similarity_matrix
from .document_access_service import get_accessible_document_ids

logger = logging.getLogger(__name__)

ENTITIES_PER_PAGE = 24
RELATIONSHIPS_PER_PAGE = 24
CITATIONS_LIMIT = 100
GRAPH_NODE_LIMIT = 120

# Cap on distinct slices in the Dashboard's "Topics by Category" chart -
# same "fold the long tail into Other" precedent as
# stats_service.DOCUMENT_TYPE_COLORS, so a user with a dozen LLM-invented
# entity_type strings still gets a readable chart, not a dozen slivers.
KNOWLEDGE_CATEGORY_CHART_LIMIT = 5

# Fetch cap before Python-side Topic grouping - generous for current
# scale, same "cap for readability/perf, not correctness" precedent as
# GRAPH_NODE_LIMIT below.
KNOWLEDGE_MAX_ENTITIES = 2000

# How many recently-processed accessible documents the Duplicate
# Knowledge insight will embed-compare - same order-of-magnitude
# precedent as AI Tasks' 100-document run cap.
KNOWLEDGE_INSIGHTS_DOC_LIMIT = 200

# Stricter than AI Tasks' default 0.85 similarity_threshold - "flag
# this as possibly the same document" should be a higher bar than
# "these are similar enough to group together" for Find Similar.
DUPLICATE_SIMILARITY_THRESHOLD = 0.92

# Keyword -> business-friendly bucket for grouping a topic's connected
# documents. There is no fixed document-type taxonomy in this codebase
# (Category/Tag are free-form, user-created labels) - this is a
# best-effort presentation heuristic over whatever labels a document
# already has, not a data-integrity feature. Checked in order; the
# first match wins. Anything unmatched (including uncategorized
# documents) falls into OTHER_DOCUMENTS_BUCKET, never hidden.
DOCUMENT_BUCKET_RULES = (
    ("Policies", ("policy", "policies")),
    ("Procedures & SOPs", ("sop", "procedure", "process")),
    ("Manuals & Guides", ("manual", "guide", "handbook")),
    ("Reports", ("report",)),
)
OTHER_DOCUMENTS_BUCKET = "Other Related Documents"

# graph_extraction_service.SUPPORTED_ENTITY_TYPES includes ORGANIZATION
# but has no separate TEAM/DEPARTMENT type - "Related Teams" reuses it
# as a heuristic (an ORGANIZATION entity may be a company, vendor, or
# internal team; the extractor doesn't distinguish), the same
# free-form/LLM-provided framing CLAUDE.md already documents for
# entity_type generally.
TEAM_ENTITY_TYPE = "ORGANIZATION"

# One color per graph_extraction_service.SUPPORTED_ENTITY_TYPES, reusing
# the exact hex values analytics.html's chart palette already
# established (same primary/info/success/warning/accent/rose set) so an
# entity-type color means the same thing everywhere in the app, not a
# second palette invented just for the graph. entity_type is free-form
# (not a DB-enforced choice - see Entity's docstring), so a type outside
# this dict (a custom LLM-provided one) falls back to
# ENTITY_TYPE_FALLBACK_COLOR rather than erroring.
ENTITY_TYPE_COLORS = {
    "PERSON": "#8B1E2D",
    "ORGANIZATION": "#2A78D6",
    "LOCATION": "#1F7A4D",
    "DATE": "#C77700",
    "PRODUCT": "#4A3AA7",
    "EVENT": "#D6336C",
    "MISC": "#6D1B27",
}
ENTITY_TYPE_FALLBACK_COLOR = "#8a7d7d"


def get_entity_type_color(entity_type):
    return ENTITY_TYPE_COLORS.get(entity_type, ENTITY_TYPE_FALLBACK_COLOR)


# Related-documents tuning for get_document_knowledge() - looser than
# DUPLICATE_SIMILARITY_THRESHOLD above ("related content" is a lower bar
# than "flag as possibly the same document").
DOCUMENT_SIMILAR_CANDIDATE_LIMIT = 200
DOCUMENT_SIMILARITY_THRESHOLD = 0.80
RELATED_DOCUMENTS_LIMIT = 8


# ==========================================================================
# Shared scoping/grouping primitives
# ==========================================================================

def _visible_entity_ids(accessible_document_ids):
    """Every Entity id with at least one mention in a document `user` can access - the one join every function below is built on."""

    return set(
        EntityMention.objects.filter(chunk__document_id__in=accessible_document_ids)
        .values_list("entity_id", flat=True)
        .distinct()
    )


def _entity_document_map(entity_ids, accessible_document_ids):
    """{entity_id: {accessible document ids that entity is mentioned in}} - the building block for every document_count/connected-documents computation below."""

    if not entity_ids:
        return {}

    pairs = (
        EntityMention.objects.filter(entity_id__in=entity_ids, chunk__document_id__in=accessible_document_ids)
        .values_list("entity_id", "chunk__document_id")
        .distinct()
    )

    mapping = defaultdict(set)
    for entity_id, document_id in pairs:
        mapping[entity_id].add(document_id)

    return mapping


def _group_into_topics(entities, doc_map):
    """Groups already-visible Entity rows by (name, entity_type) into Topic dicts - see the module docstring for why this is safe without re-normalizing anything."""

    groups = defaultdict(list)
    for entity in entities:
        groups[(entity.name, entity.entity_type)].append(entity)

    topics = []
    for members in groups.values():
        members.sort(key=lambda e: e.mention_count, reverse=True)
        top = members[0]

        doc_ids = set()
        for member in members:
            doc_ids |= doc_map.get(member.id, set())

        topics.append({
            "id": top.id,
            "display_name": top.display_name,
            "entity_type": top.entity_type,
            "color": get_entity_type_color(top.entity_type),
            "mention_count": sum(e.mention_count for e in members),
            "entity_ids": [e.id for e in members],
            "member_count": len(members),
            "document_count": len(doc_ids),
        })

    return topics


def _build_topic_dataset(user):
    """
    Shared computation behind every Topic-level read: the viewer's
    accessible scope, its visible entities merged into Topics, and the
    fully-visible relationship edges between them (both endpoints must
    themselves be visible - an edge extracted from one accessible
    document can still name an entity that only appears in a document
    this viewer can't see, and that neighbor must not leak). Every
    Knowledge Center page/insight that needs "the topics this user can
    see" goes through this one function so the merge logic only lives
    in one place.
    """

    accessible_document_ids = get_accessible_document_ids(user)

    if not accessible_document_ids:
        return {
            "accessible_document_ids": set(),
            "visible_entity_ids": set(),
            "entities": [],
            "topics": [],
            "topics_by_key": {},
            "entity_to_topic_key": {},
            "relationships": [],
        }

    visible_entity_ids = _visible_entity_ids(accessible_document_ids)

    entities = list(
        Entity.objects.filter(id__in=visible_entity_ids).order_by("-mention_count")[:KNOWLEDGE_MAX_ENTITIES]
    )

    doc_map = _entity_document_map([e.id for e in entities], accessible_document_ids)
    topics = _group_into_topics(entities, doc_map)

    entities_by_id = {e.id: e for e in entities}
    entity_to_topic_key = {e.id: (e.name, e.entity_type) for e in entities}

    # Keyed by (Entity.name, entity_type) - the same normalized key
    # entity_to_topic_key uses - not display_name, which isn't
    # guaranteed unique.
    topics_by_key = {}
    for topic in topics:
        top_entity = entities_by_id.get(topic["id"])
        if top_entity is not None:
            topics_by_key[(top_entity.name, top_entity.entity_type)] = topic

    relationships = list(
        Relationship.objects.filter(source_id__in=visible_entity_ids, target_id__in=visible_entity_ids)
        .select_related("source", "target")
    )

    return {
        "accessible_document_ids": accessible_document_ids,
        "visible_entity_ids": visible_entity_ids,
        "entities": entities,
        "topics": topics,
        "topics_by_key": topics_by_key,
        "entity_to_topic_key": entity_to_topic_key,
        "relationships": relationships,
    }


def _dedupe_relationship_rows(relationships, other_field):
    """
    Collapses relationship rows that point at different uploaders'
    copies of the same real-world entity down to one row (the
    highest-weight one - `relationships` must already be ordered by
    -weight), so a topic's Connected Concepts panel shows one entry per
    distinct concept, not one per uploader.
    """

    seen = set()
    rows = []

    for rel in relationships:
        other = getattr(rel, other_field)
        key = (other.name, other.entity_type, rel.relation_type)
        if key in seen:
            continue
        seen.add(key)
        rows.append(rel)

    return rows


def _bucket_documents(documents):
    """Groups `documents` into business-friendly buckets per DOCUMENT_BUCKET_RULES - see that constant's docstring. Returns [(bucket_label, [documents]), ...], non-empty buckets only, in a stable priority order."""

    buckets = {label: [] for label, _ in DOCUMENT_BUCKET_RULES}
    other = []

    for document in documents:
        labels = [document.category.name.lower()] if document.category_id else []
        labels += [tag.name.lower() for tag in document.tags.all()]
        combined = " ".join(labels)

        matched_bucket = None
        for label, keywords in DOCUMENT_BUCKET_RULES:
            if any(keyword in combined for keyword in keywords):
                matched_bucket = label
                break

        (buckets[matched_bucket] if matched_bucket else other).append(document)

    ordered = [(label, buckets[label]) for label, _ in DOCUMENT_BUCKET_RULES if buckets[label]]
    if other:
        ordered.append((OTHER_DOCUMENTS_BUCKET, other))

    return ordered


# ==========================================================================
# Explore Topics
# ==========================================================================

def get_knowledge_overview(user, dataset=None):
    """
    Summary counts + category breakdown for Explore Topics.

    total_accessible_documents/indexed_documents are real, untruncated
    counts (a plain .count() query) - deliberately NOT derived from
    get_knowledge_insights()'s `not_processed` list, which is capped at
    8 rows for display and would silently under-report past that.

    `dataset`, when provided (an already-built _build_topic_dataset()
    result), is used as-is instead of rebuilding it - lets a caller
    that needs more than one of get_knowledge_overview()/
    get_knowledge_insights()/search_topics() in the same request (e.g.
    knowledge_base_view) build the ~5-query dataset once and share it,
    instead of each function rebuilding it independently.
    """

    if dataset is None:
        dataset = _build_topic_dataset(user)
    topics = dataset["topics"]
    accessible_document_ids = dataset["accessible_document_ids"]

    total_sources = 0
    if accessible_document_ids:
        total_sources = (
            EntityMention.objects.filter(
                entity_id__in=dataset["visible_entity_ids"],
                chunk__document_id__in=accessible_document_ids,
            )
            .values("chunk__document_id")
            .distinct()
            .count()
        )

    total_accessible_documents = len(accessible_document_ids)
    indexed_documents = 0
    if accessible_document_ids:
        indexed_documents = Document.objects.filter(
            id__in=accessible_document_ids, processing_status=Document.ProcessingStatus.COMPLETED
        ).count()

    categories = Counter(t["entity_type"] for t in topics)
    category_breakdown = _build_category_breakdown(categories)

    return {
        "total_entities": len(topics),
        "total_relationships": len(dataset["relationships"]),
        "total_sources": total_sources,
        "total_accessible_documents": total_accessible_documents,
        "indexed_documents": indexed_documents,
        "indexed_documents_label": f"of {total_accessible_documents} document{'' if total_accessible_documents == 1 else 's'}",
        "categories": [
            {"entity_type": k, "count": v, "color": get_entity_type_color(k)} for k, v in categories.most_common()
        ],
        "category_breakdown": category_breakdown,
    }


def _build_category_breakdown(categories):
    """
    Top KNOWLEDGE_CATEGORY_CHART_LIMIT entity_type counts, colored via
    the same get_entity_type_color() the Knowledge Graph visualization
    uses, with any remaining types folded into one "Other" slice -
    feeds the Dashboard's "Topics by Category" chart (_knowledge_snapshot.html).
    """

    ranked = categories.most_common()
    top = ranked[:KNOWLEDGE_CATEGORY_CHART_LIMIT]
    other_count = sum(count for _, count in ranked[KNOWLEDGE_CATEGORY_CHART_LIMIT:])

    breakdown = [
        {"entity_type": entity_type, "count": count, "color": get_entity_type_color(entity_type)}
        for entity_type, count in top
    ]
    if other_count:
        breakdown.append({"entity_type": "Other", "count": other_count, "color": ENTITY_TYPE_FALLBACK_COLOR})

    total = sum(item["count"] for item in breakdown)
    for item in breakdown:
        item["percent"] = round((item["count"] / total) * 100) if total else 0

    return breakdown


def search_topics(user, query="", entity_type="", page=1, dataset=None):
    """
    Paginated, optionally filtered Topic list, ordered by aggregated
    mention count.

    `dataset`, when provided, supplies the already-computed
    accessible_document_ids/visible_entity_ids instead of recomputing
    them - see get_knowledge_overview()'s docstring for why. The
    entity query itself still runs fresh (query/entity_type filtering
    needs to happen in the database, not by re-filtering an
    already-fetched Python list).
    """

    if dataset is not None:
        accessible_document_ids = dataset["accessible_document_ids"]
        visible_entity_ids = dataset["visible_entity_ids"]
    else:
        accessible_document_ids = get_accessible_document_ids(user)
        visible_entity_ids = _visible_entity_ids(accessible_document_ids) if accessible_document_ids else set()

    if not accessible_document_ids:
        return Paginator([], ENTITIES_PER_PAGE).get_page(page)

    entities = Entity.objects.filter(id__in=visible_entity_ids)

    if query:
        entities = entities.filter(display_name__icontains=query)

    if entity_type:
        entities = entities.filter(entity_type=entity_type)

    entities = list(entities.order_by("-mention_count", "display_name")[:KNOWLEDGE_MAX_ENTITIES])

    doc_map = _entity_document_map([e.id for e in entities], accessible_document_ids)
    topics = _group_into_topics(entities, doc_map)
    topics.sort(key=lambda t: (-t["mention_count"], t["display_name"]))

    return Paginator(topics, ENTITIES_PER_PAGE).get_page(page)


def list_all_topics(user):
    """
    Every Topic visible to `user`, unpaginated (bounded by
    KNOWLEDGE_MAX_ENTITIES) and sorted by mention count - for CSV
    export (Reports) and other whole-list consumers, as opposed to
    search_topics()'s paginated Explore Topics page.
    """

    dataset = _build_topic_dataset(user)

    return sorted(dataset["topics"], key=lambda t: (-t["mention_count"], t["display_name"]))


# ==========================================================================
# Topic Detail
# ==========================================================================

def get_topic_detail(user, entity_id):
    """
    A Topic's full detail view: overview, connected documents (bucketed),
    related teams, connected concepts (relationships), cross-references,
    timeline, and citations - or None if `entity_id` doesn't exist or
    isn't visible to `user`.
    """

    dataset = _build_topic_dataset(user)

    if entity_id not in dataset["visible_entity_ids"]:
        return None

    anchor = Entity.objects.filter(id=entity_id).first()
    if anchor is None:
        return None

    topic = dataset["topics_by_key"].get((anchor.name, anchor.entity_type))
    entity_ids = topic["entity_ids"] if topic else [anchor.id]

    accessible_document_ids = dataset["accessible_document_ids"]
    visible_entity_ids = dataset["visible_entity_ids"]

    members = list(Entity.objects.filter(id__in=entity_ids).order_by("-mention_count"))
    top = members[0] if members else anchor

    doc_map = _entity_document_map(entity_ids, accessible_document_ids)
    own_document_ids = set()
    for ids in doc_map.values():
        own_document_ids |= ids

    documents = list(
        Document.objects.filter(id__in=own_document_ids).select_related("category").prefetch_related("tags")
    )

    mentions = list(
        EntityMention.objects.filter(entity_id__in=entity_ids, chunk__document_id__in=accessible_document_ids)
        .select_related("chunk", "chunk__document")
        .order_by("-created_at")[:40]
    )

    outgoing_all = list(
        Relationship.objects.filter(source_id__in=entity_ids, target_id__in=visible_entity_ids)
        .exclude(target_id__in=entity_ids)
        .select_related("target")
        .order_by("-weight")
    )
    incoming_all = list(
        Relationship.objects.filter(target_id__in=entity_ids, source_id__in=visible_entity_ids)
        .exclude(source_id__in=entity_ids)
        .select_related("source")
        .order_by("-weight")
    )

    outgoing = _dedupe_relationship_rows(outgoing_all, "target")[:20]
    incoming = _dedupe_relationship_rows(incoming_all, "source")[:20]

    related_teams = _related_teams(outgoing, incoming)
    cross_reference_documents = _cross_reference_documents(
        outgoing, incoming, accessible_document_ids, exclude_document_ids=own_document_ids
    )
    timeline = _topic_timeline(mentions[:20], outgoing[:10] + incoming[:10])

    chunk_keys = {(m.chunk.document.title, m.chunk.chunk_number) for m in mentions}
    citations = [c for c in get_citation_explorer(user) if (c["document"], c["chunk_number"]) in chunk_keys][:20]

    return {
        "entity": top,
        "member_count": len(members),
        "mention_count": sum(e.mention_count for e in members),
        "document_count": len(own_document_ids),
        "document_buckets": _bucket_documents(documents),
        "related_teams": related_teams,
        "outgoing": outgoing,
        "incoming": incoming,
        "cross_reference_documents": cross_reference_documents,
        "timeline": timeline,
        "citations": citations,
        "mentions": mentions[:20],
    }


def _related_teams(outgoing, incoming, limit=10):
    """One-hop-connected entities of TEAM_ENTITY_TYPE, deduped, most-mentioned first."""

    teams = {}
    for rel in outgoing:
        if rel.target.entity_type == TEAM_ENTITY_TYPE:
            teams[rel.target.name] = rel.target
    for rel in incoming:
        if rel.source.entity_type == TEAM_ENTITY_TYPE:
            teams[rel.source.name] = rel.source

    return sorted(teams.values(), key=lambda e: -e.mention_count)[:limit]


def _cross_reference_documents(outgoing, incoming, accessible_document_ids, exclude_document_ids, limit=20):
    """Documents that mention a one-hop-connected entity but don't directly mention this topic - "related through a connection," not a direct match."""

    neighbor_ids = {rel.target_id for rel in outgoing} | {rel.source_id for rel in incoming}

    if not neighbor_ids:
        return []

    doc_map = _entity_document_map(list(neighbor_ids), accessible_document_ids)
    doc_ids = set()
    for ids in doc_map.values():
        doc_ids |= ids
    doc_ids -= exclude_document_ids

    if not doc_ids:
        return []

    return list(Document.objects.filter(id__in=doc_ids).select_related("category")[:limit])


def _topic_timeline(mentions, relationships, limit=20):
    """Chronological feed of when this topic's supporting content was ingested and when its connections were first found/last reinforced - all from fields that already exist."""

    events = []

    for mention in mentions:
        events.append({
            "at": mention.created_at,
            "kind": "mention",
            "description": f'Linked to "{mention.chunk.document.title}" (chunk {mention.chunk.chunk_number})',
        })

    for rel in relationships:
        events.append({
            "at": rel.updated_at,
            "kind": "relationship",
            "description": f'Connection "{rel.relation_type}" reinforced x{rel.weight}' if rel.weight > 1
            else f'Connection "{rel.relation_type}" first found',
        })

    events.sort(key=lambda e: e["at"], reverse=True)

    return events[:limit]


# ==========================================================================
# Relationship Explorer
# ==========================================================================

def get_relationships(user, relation_type="", page=1):
    """Paginated relationship list, both endpoints visible to `user`, most-reinforced first."""

    accessible_document_ids = get_accessible_document_ids(user)

    if not accessible_document_ids:
        return Paginator([], RELATIONSHIPS_PER_PAGE).get_page(page)

    visible_entity_ids = _visible_entity_ids(accessible_document_ids)

    relationships = (
        Relationship.objects.filter(source_id__in=visible_entity_ids, target_id__in=visible_entity_ids)
        .select_related("source", "target")
    )

    if relation_type:
        relationships = relationships.filter(relation_type=relation_type)

    return Paginator(relationships, RELATIONSHIPS_PER_PAGE).get_page(page)


def get_relation_types(user):
    """Distinct relation_type values visible to `user`, for the Relationship Explorer's filter dropdown."""

    accessible_document_ids = get_accessible_document_ids(user)

    if not accessible_document_ids:
        return []

    visible_entity_ids = _visible_entity_ids(accessible_document_ids)

    return list(
        Relationship.objects.filter(source_id__in=visible_entity_ids, target_id__in=visible_entity_ids)
        .values_list("relation_type", flat=True)
        .distinct()
        .order_by("relation_type")
    )


# ==========================================================================
# Knowledge Graph View
# ==========================================================================

def get_graph_data(user):
    """Nodes/edges for the Knowledge Graph visualization, shaped for vis-network - Topic-granularity (not raw Entity rows), capped at GRAPH_NODE_LIMIT by mention count."""

    dataset = _build_topic_dataset(user)

    topics = sorted(dataset["topics"], key=lambda t: -t["mention_count"])[:GRAPH_NODE_LIMIT]

    entity_to_topic = {}
    for topic in topics:
        for entity_id in topic["entity_ids"]:
            entity_to_topic[entity_id] = topic["id"]

    edge_agg = {}
    for rel in dataset["relationships"]:
        topic_from = entity_to_topic.get(rel.source_id)
        topic_to = entity_to_topic.get(rel.target_id)
        if topic_from is None or topic_to is None or topic_from == topic_to:
            continue
        agg = edge_agg.setdefault((topic_from, topic_to), {"weight": 0, "labels": Counter()})
        agg["weight"] += rel.weight
        agg["labels"][rel.relation_type] += rel.weight

    nodes = [
        {
            "id": topic["id"],
            "label": topic["display_name"],
            "group": topic["entity_type"],
            "value": max(topic["mention_count"], 1),
        }
        for topic in topics
    ]

    edges = [
        {"from": frm, "to": to, "label": agg["labels"].most_common(1)[0][0], "value": agg["weight"]}
        for (frm, to), agg in edge_agg.items()
    ]

    return {"nodes": nodes, "edges": edges}


def get_graph_insights(user):
    """A handful of real, computed-not-fabricated stats about the shape of the viewer's visible knowledge graph, at Topic granularity."""

    dataset = _build_topic_dataset(user)
    topics = dataset["topics"]
    relationships = dataset["relationships"]
    entity_to_topic_key = dataset["entity_to_topic_key"]
    topics_by_key = dataset["topics_by_key"]

    most_mentioned = max(topics, key=lambda t: t["mention_count"], default=None)

    degree = Counter()
    for rel in relationships:
        source_key = entity_to_topic_key.get(rel.source_id)
        target_key = entity_to_topic_key.get(rel.target_id)
        if source_key and target_key and source_key != target_key:
            degree[source_key] += 1
            degree[target_key] += 1

    most_connected = None
    if degree:
        top_key, top_degree = degree.most_common(1)[0]
        top_topic = topics_by_key.get(top_key)
        if top_topic:
            most_connected = {"entity": top_topic, "degree": top_degree}

    top_category_counts = Counter(t["entity_type"] for t in topics).most_common(1)
    top_relation_counts = Counter(r.relation_type for r in relationships).most_common(1)

    return {
        "total_entities": len(topics),
        "total_relationships": len(relationships),
        "most_mentioned_entity": most_mentioned,
        "most_connected": most_connected,
        "top_category": (
            {"entity_type": top_category_counts[0][0], "count": top_category_counts[0][1]}
            if top_category_counts else None
        ),
        "top_relation": (
            {"relation_type": top_relation_counts[0][0], "count": top_relation_counts[0][1]}
            if top_relation_counts else None
        ),
    }


def get_topic_node_detail(user, entity_id):
    """
    Trimmed, JSON-serializable subset of get_topic_detail() for the
    Knowledge Graph's click-a-node side panel - reuses that function
    rather than re-querying, just shapes/caps the result for an inline
    preview instead of the full Topic Detail page (which stays one
    click away via "detail_url").
    """

    detail = get_topic_detail(user, entity_id)
    if detail is None:
        return None

    entity = detail["entity"]
    documents = [doc for _, docs in detail["document_buckets"] for doc in docs][:6]

    return {
        "id": entity.id,
        "display_name": entity.display_name,
        "entity_type": entity.entity_type,
        "color": get_entity_type_color(entity.entity_type),
        "mention_count": detail["mention_count"],
        "document_count": detail["document_count"],
        "documents": [{"id": d.id, "title": d.title} for d in documents],
        "related_teams": [{"id": t.id, "display_name": t.display_name} for t in detail["related_teams"][:5]],
        "outgoing": [
            {"relation_type": r.relation_type, "target": r.target.display_name, "target_id": r.target_id, "weight": r.weight}
            for r in detail["outgoing"][:6]
        ],
        "incoming": [
            {"relation_type": r.relation_type, "source": r.source.display_name, "source_id": r.source_id, "weight": r.weight}
            for r in detail["incoming"][:6]
        ],
        "detail_url": reverse("entity_detail", args=[entity.id]),
    }


def get_topic_pair_relationship_detail(user, topic_a_id, topic_b_id):
    """
    The underlying Relationship rows between two Topics' member
    entities (either direction) - for the Knowledge Graph's
    click-an-edge side panel. Reuses _build_topic_dataset's already-
    computed topic membership and visible-relationship set rather than
    re-querying; returns None if either topic id doesn't resolve to a
    visible Topic.
    """

    dataset = _build_topic_dataset(user)

    entity_a = Entity.objects.filter(id=topic_a_id).first()
    entity_b = Entity.objects.filter(id=topic_b_id).first()
    if entity_a is None or entity_b is None:
        return None

    topic_a = dataset["topics_by_key"].get((entity_a.name, entity_a.entity_type))
    topic_b = dataset["topics_by_key"].get((entity_b.name, entity_b.entity_type))
    if topic_a is None or topic_b is None:
        return None

    a_ids = set(topic_a["entity_ids"])
    b_ids = set(topic_b["entity_ids"])

    rows = [
        rel for rel in dataset["relationships"]
        if (rel.source_id in a_ids and rel.target_id in b_ids)
        or (rel.source_id in b_ids and rel.target_id in a_ids)
    ]
    rows.sort(key=lambda r: -r.weight)

    return {
        "topic_a": {"id": topic_a["id"], "display_name": topic_a["display_name"]},
        "topic_b": {"id": topic_b["id"], "display_name": topic_b["display_name"]},
        "relationships": [
            {
                "source": r.source.display_name,
                "relation_type": r.relation_type,
                "target": r.target.display_name,
                "weight": r.weight,
                "context": r.context[:280],
            }
            for r in rows[:15]
        ],
        "total": len(rows),
    }


# ==========================================================================
# Citation Viewer
# ==========================================================================

def get_citation_explorer(user):
    """
    Every distinct (document, chunk_number) actually cited across this
    user's own Q&A history (QueryLog.sources' citation_number), most
    recent question first. QueryLog is inherently personal ("questions
    I asked"), so - unlike everything else in this module - this is
    correctly scoped by `user` already, not by document accessibility.
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


def resolve_topics_for_citations(user, citations):
    """
    Best-effort cross-link from a cited (document title, chunk_number)
    back to its Topic Detail page, for the Citation Viewer. Annotates
    each citation dict in place with a `topic_id` key (None if no
    visible entity was extracted from that specific chunk) - a
    convenience link when resolvable, never a hard requirement, same
    "enrich the dict in place" pattern citation_service.extract_citations()
    already uses for `citation_number`.
    """

    if not citations:
        return citations

    accessible_document_ids = get_accessible_document_ids(user)

    if not accessible_document_ids:
        for citation in citations:
            citation["topic_id"] = None
        return citations

    titles = {c["document"] for c in citations if c.get("document")}
    numbers = {c["chunk_number"] for c in citations if c.get("chunk_number")}

    key_to_entity_id = {}
    if titles and numbers:
        mentions = (
            EntityMention.objects.filter(
                chunk__document_id__in=accessible_document_ids,
                chunk__document__title__in=titles,
                chunk__chunk_number__in=numbers,
            ).select_related("chunk__document")
        )
        for mention in mentions:
            key = (mention.chunk.document.title, mention.chunk.chunk_number)
            key_to_entity_id.setdefault(key, mention.entity_id)

    for citation in citations:
        key = (citation.get("document"), citation.get("chunk_number"))
        citation["topic_id"] = key_to_entity_id.get(key)

    return citations


def get_related_topics_for_citations(user, citations, limit=6):
    """
    Up to `limit` distinct entities mentioned in the cited chunks of an
    Ask AI answer, most-mentioned first - "Related Topics" for the
    answer card, at zero extra LLM cost (same knowledge graph
    resolve_topics_for_citations() above already queries, just grouped
    into a list of {id, name} instead of a per-citation topic_id).
    Same accessible-document scoping rule as everything else in this
    file - see the module docstring.
    """

    if not citations:
        return []

    accessible_document_ids = get_accessible_document_ids(user)

    if not accessible_document_ids:
        return []

    titles = {c["document"] for c in citations if c.get("document")}
    numbers = {c["chunk_number"] for c in citations if c.get("chunk_number")}

    if not titles or not numbers:
        return []

    entity_ids = (
        EntityMention.objects.filter(
            chunk__document_id__in=accessible_document_ids,
            chunk__document__title__in=titles,
            chunk__chunk_number__in=numbers,
        ).values_list("entity_id", flat=True).distinct()
    )

    entities = Entity.objects.filter(id__in=entity_ids).order_by("-mention_count")[:limit]

    return [{"id": entity.id, "name": entity.display_name} for entity in entities]


# ==========================================================================
# Knowledge Insights
# ==========================================================================

def get_knowledge_insights(user, dataset=None):
    """
    Read-only aggregates over the viewer's accessible knowledge - no
    LLM calls (that's Document Analysis, which belongs to AI Tasks, not
    here). See knowledge_service module docstring / CLAUDE.md for which
    insights are genuinely buildable this way and which are
    intentionally deferred (missing/conflicting information).

    `dataset`, when provided, is used as-is - see
    get_knowledge_overview()'s docstring.
    """

    if dataset is None:
        dataset = _build_topic_dataset(user)
    accessible_document_ids = dataset["accessible_document_ids"]

    if not accessible_document_ids:
        return _empty_insights()

    topics = dataset["topics"]
    relationships = dataset["relationships"]
    entity_to_topic_key = dataset["entity_to_topic_key"]
    topics_by_key = dataset["topics_by_key"]

    most_referenced_documents = list(
        Document.objects.filter(id__in=accessible_document_ids)
        .annotate(mention_total=Count("chunks__entity_mentions", distinct=True))
        .filter(mention_total__gt=0)
        .order_by("-mention_total")[:8]
    )

    degree = Counter()
    for rel in relationships:
        source_key = entity_to_topic_key.get(rel.source_id)
        target_key = entity_to_topic_key.get(rel.target_id)
        if source_key and target_key and source_key != target_key:
            degree[source_key] += 1
            degree[target_key] += 1

    frequently_connected_topics = [
        {**topics_by_key[key], "degree": count}
        for key, count in degree.most_common(8)
        if key in topics_by_key
    ]

    recent_mentions = list(
        EntityMention.objects.filter(
            entity_id__in=dataset["visible_entity_ids"], chunk__document_id__in=accessible_document_ids
        ).select_related("entity", "chunk__document").order_by("-created_at")[:8]
    )
    recent_relationships = list(
        Relationship.objects.filter(source_id__in=dataset["visible_entity_ids"], target_id__in=dataset["visible_entity_ids"])
        .select_related("source", "target").order_by("-updated_at")[:8]
    )
    recently_updated = sorted(
        [
            {"kind": "mention", "at": m.created_at, "entity": m.entity, "document": m.chunk.document}
            for m in recent_mentions
        ] + [
            {"kind": "relationship", "at": r.updated_at, "relationship": r}
            for r in recent_relationships
        ],
        key=lambda e: e["at"], reverse=True,
    )[:8]

    accessible_documents = Document.objects.filter(id__in=accessible_document_ids)
    not_processed = list(accessible_documents.exclude(processing_status=Document.ProcessingStatus.COMPLETED)[:8])
    processed_without_extraction = list(
        accessible_documents.filter(processing_status=Document.ProcessingStatus.COMPLETED, chunk_count__gt=0)
        .annotate(mention_total=Count("chunks__entity_mentions", distinct=True))
        .filter(mention_total=0)[:8]
    )

    strong_topic_keys = {entity_to_topic_key[e.id] for e in dataset["entities"] if e.mention_count > 1}
    weak_topic_keys = {entity_to_topic_key[e.id] for e in dataset["entities"] if e.mention_count <= 1}
    weak_topics = [
        topics_by_key[key] for key in (weak_topic_keys - strong_topic_keys) if key in topics_by_key
    ][:8]

    duplicate_clusters = _duplicate_document_clusters(accessible_document_ids)

    return {
        "most_referenced_documents": most_referenced_documents,
        "frequently_connected_topics": frequently_connected_topics,
        "recently_updated": recently_updated,
        "not_processed": not_processed,
        "processed_without_extraction": processed_without_extraction,
        "weak_topics": weak_topics,
        "duplicate_clusters": duplicate_clusters,
        "total_accessible_documents": accessible_documents.count(),
        "total_topics": len(topics),
    }


def _empty_insights():
    return {
        "most_referenced_documents": [],
        "frequently_connected_topics": [],
        "recently_updated": [],
        "not_processed": [],
        "processed_without_extraction": [],
        "weak_topics": [],
        "duplicate_clusters": [],
        "total_accessible_documents": 0,
        "total_topics": 0,
    }


def _duplicate_document_clusters(accessible_document_ids, limit=KNOWLEDGE_INSIGHTS_DOC_LIMIT):
    """
    Reuses ai_tasks_similarity_service's already-computed ChunkEmbedding
    rows (pure numpy, no LLM call, no re-embedding) to flag near-duplicate
    accessible documents - exactly "reuse embeddings, don't duplicate
    functionality." Never raises: an embedding failure for one document
    just excludes it, matching that service's own None-on-missing
    contract.
    """

    documents = list(
        Document.objects.filter(id__in=accessible_document_ids, processing_status=Document.ProcessingStatus.COMPLETED)
        .order_by("-uploaded_at")[:limit]
    )

    if len(documents) < 2:
        return []

    doc_ids = []
    embeddings = []
    for document in documents:
        vector = build_document_embedding(document)
        if vector is not None:
            doc_ids.append(document.id)
            embeddings.append(vector)

    if len(embeddings) < 2:
        return []

    try:
        clusters = cluster_documents(doc_ids, embeddings, threshold=DUPLICATE_SIMILARITY_THRESHOLD)
    except Exception:
        logger.exception("Duplicate knowledge detection failed")
        return []

    if not clusters:
        return []

    documents_by_id = {d.id: d for d in documents}

    return [
        {"documents": [documents_by_id[i] for i in cluster["document_ids"] if i in documents_by_id]}
        for cluster in clusters
    ]


# ==========================================================================
# Document Relationship View
# ==========================================================================

def get_document_knowledge(user, document):
    """
    Everything the Document Relationship View needs for one document:
    the topics/entities extracted from it, relationships among them,
    related documents via shared topics (entity-graph-based) and via
    semantic similarity (embedding-based - reuses
    ai_tasks_similarity_service's exact math, the same functions
    _duplicate_document_clusters above already uses, just scored
    pairwise against one document instead of clustered wholesale), and
    citations from the viewer's own Ask AI history that referenced it.

    Returns None if `document` isn't in `user`'s accessible scope -
    callers should already have checked
    document_access_service.can_view_document() before calling this,
    this is a defense-in-depth second check on the same rule.
    """

    dataset = _build_topic_dataset(user)
    accessible_document_ids = dataset["accessible_document_ids"]

    if document.id not in accessible_document_ids:
        return None

    entity_to_topic_key = dataset["entity_to_topic_key"]
    topics_by_key = dataset["topics_by_key"]

    doc_entity_ids = set(
        EntityMention.objects.filter(chunk__document=document, entity_id__in=dataset["visible_entity_ids"])
        .values_list("entity_id", flat=True).distinct()
    )

    doc_topic_keys = {entity_to_topic_key[eid] for eid in doc_entity_ids if eid in entity_to_topic_key}
    topics = sorted(
        (topics_by_key[key] for key in doc_topic_keys if key in topics_by_key),
        key=lambda t: -t["mention_count"],
    )

    topic_entity_ids = set()
    for key in doc_topic_keys:
        topic = topics_by_key.get(key)
        if topic:
            topic_entity_ids.update(topic["entity_ids"])

    relationships = _dedupe_topic_pair_relationships(
        [
            rel for rel in dataset["relationships"]
            if rel.source_id in topic_entity_ids and rel.target_id in topic_entity_ids and rel.source_id != rel.target_id
        ],
        entity_to_topic_key,
    )

    related_by_topic = _related_documents_by_shared_topic(
        topic_entity_ids, accessible_document_ids, exclude_document_id=document.id
    )
    similar_documents = _similar_documents_by_embedding(document, accessible_document_ids)

    citations = [c for c in get_citation_explorer(user) if c["document"] == document.title][:20]

    return {
        "document": document,
        "topics": topics,
        "relationships": relationships[:20],
        "related_by_topic": related_by_topic,
        "similar_documents": similar_documents,
        "citations": citations,
    }


def _dedupe_topic_pair_relationships(relationships, entity_to_topic_key):
    """Collapses relationship rows that resolve to the same (topic, topic, relation_type) triple down to the highest-weight one - Relationship's default ordering is already -weight, so first-seen-per-key wins, same pattern as _dedupe_relationship_rows."""

    seen = set()
    rows = []

    for rel in relationships:
        key = (entity_to_topic_key.get(rel.source_id), entity_to_topic_key.get(rel.target_id), rel.relation_type)
        if key in seen:
            continue
        seen.add(key)
        rows.append(rel)

    return rows


def _related_documents_by_shared_topic(topic_entity_ids, accessible_document_ids, exclude_document_id, limit=RELATED_DOCUMENTS_LIMIT):
    """Other accessible documents mentioning the same topics as this one, ranked by how many topics they share - reuses _entity_document_map rather than a new query shape."""

    if not topic_entity_ids:
        return []

    doc_map = _entity_document_map(list(topic_entity_ids), accessible_document_ids)

    shared_counts = Counter()
    for document_ids in doc_map.values():
        for document_id in document_ids:
            if document_id != exclude_document_id:
                shared_counts[document_id] += 1

    ranked_ids = [doc_id for doc_id, _ in shared_counts.most_common(limit)]
    if not ranked_ids:
        return []

    documents_by_id = {d.id: d for d in Document.objects.filter(id__in=ranked_ids)}
    order = {doc_id: i for i, doc_id in enumerate(ranked_ids)}

    return sorted(
        (
            {"document": documents_by_id[doc_id], "shared_topics": shared_counts[doc_id]}
            for doc_id in ranked_ids if doc_id in documents_by_id
        ),
        key=lambda row: order[row["document"].id],
    )


def _similar_documents_by_embedding(document, accessible_document_ids, limit=RELATED_DOCUMENTS_LIMIT, threshold=DOCUMENT_SIMILARITY_THRESHOLD):
    """
    Cosine similarity between `document`'s mean-pooled chunk embedding
    and other accessible, processed documents' - reuses
    ai_tasks_similarity_service.build_document_embedding/
    cosine_similarity_matrix exactly, the same functions
    _duplicate_document_clusters above already calls, just scored
    pairwise against one anchor document instead of clustered wholesale.
    Never raises: a missing embedding (document still processing) or a
    scoring failure returns [], never breaks the page.
    """

    anchor_vector = build_document_embedding(document)
    if anchor_vector is None:
        return []

    candidates = list(
        Document.objects.filter(id__in=accessible_document_ids, processing_status=Document.ProcessingStatus.COMPLETED)
        .exclude(id=document.id)
        .order_by("-uploaded_at")[:DOCUMENT_SIMILAR_CANDIDATE_LIMIT]
    )

    valid_candidates = []
    candidate_vectors = []
    for candidate in candidates:
        vector = build_document_embedding(candidate)
        if vector is not None:
            valid_candidates.append(candidate)
            candidate_vectors.append(vector)

    if not valid_candidates:
        return []

    try:
        matrix = cosine_similarity_matrix([anchor_vector] + candidate_vectors)
    except Exception:
        logger.exception("Similar-document scoring failed for document %s", document.id)
        return []

    scored = [
        (float(matrix[0][i + 1]), candidate)
        for i, candidate in enumerate(valid_candidates)
        if matrix[0][i + 1] >= threshold
    ]
    scored.sort(key=lambda pair: -pair[0])

    return [{"document": doc, "similarity": round(sim * 100)} for sim, doc in scored[:limit]]
