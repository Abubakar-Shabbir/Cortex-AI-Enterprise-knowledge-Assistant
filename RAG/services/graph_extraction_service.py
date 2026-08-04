"""
LLM-backed entity and relationship extraction for the knowledge graph.

extract_graph() is the only entry point other services should call.
It never raises: any failure (LLM error, malformed JSON, empty chunk)
just yields an empty GraphExtractionResult, so a bad extraction can
never break document ingestion.
"""

import json
import logging
import re
from dataclasses import dataclass, field

from .gemini_client import get_model

logger = logging.getLogger(__name__)

DEFAULT_ENTITY_TYPE = "MISC"
DEFAULT_RELATION_TYPE = "RELATED_TO"

# Chunks shorter than this rarely contain extractable relationships and
# aren't worth an LLM call.
MIN_CHUNK_LENGTH = 20

# Guidance only - entity_type is a free-form string (see Entity model),
# so the extractor is never limited to this list.
SUGGESTED_ENTITY_TYPES = (
    "PERSON",
    "ORGANIZATION",
    "LOCATION",
    "DATE",
    "PRODUCT",
    "EVENT",
    "MISC",
)

EXTRACTION_PROMPT = """You are an information extraction engine.

Read the text below and extract:
1. Named entities - people, organizations, locations, dates, products,
   events, or other significant named concepts.
2. Relationships between those entities, as (source, relation, target)
   triples, using short verb-phrase relation labels (e.g. "works_for",
   "located_in", "founded_by").

Rules:
- Only extract entities and relationships explicitly supported by the text.
- Reuse the exact entity names in both the "entities" list and the
  "relationships" triples so they can be linked.
- Suggested entity types: {entity_types}. Use "MISC" if none fit.
- If nothing qualifies, return empty lists.
- Respond with JSON only, matching this shape exactly:
{{"entities": [{{"name": "...", "type": "..."}}], "relationships": [{{"source": "...", "relation": "...", "target": "..."}}]}}

Text:
----------------
{text}
----------------
"""


@dataclass
class ExtractedEntity:
    name: str
    type: str = DEFAULT_ENTITY_TYPE


@dataclass
class ExtractedRelationship:
    source: str
    relation: str
    target: str


@dataclass
class GraphExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    relationships: list[ExtractedRelationship] = field(default_factory=list)


def normalize_entity_name(name: str) -> str:
    """Collapse whitespace and trim. Preserves original casing for display."""

    return re.sub(r"\s+", " ", (name or "")).strip()


def normalize_entity_key(name: str) -> str:
    """Canonical, case-insensitive form used to deduplicate entities."""

    return normalize_entity_name(name).lower()


def normalize_entity_type(entity_type: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", (entity_type or "").strip())
    cleaned = cleaned.strip("_").upper()

    return cleaned or DEFAULT_ENTITY_TYPE


def normalize_relation_type(relation: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9]+", "_", (relation or "").strip())
    cleaned = cleaned.strip("_").upper()

    return cleaned or DEFAULT_RELATION_TYPE


def _parse_response(raw_text: str) -> GraphExtractionResult:

    try:
        payload = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Graph extraction: could not parse LLM JSON output: %s", exc)
        return GraphExtractionResult()

    if not isinstance(payload, dict):
        logger.warning("Graph extraction: LLM output was not a JSON object")
        return GraphExtractionResult()

    entities: list[ExtractedEntity] = []

    for item in payload.get("entities") or []:

        if not isinstance(item, dict):
            continue

        name = normalize_entity_name(item.get("name", ""))

        if not name:
            continue

        entities.append(
            ExtractedEntity(
                name=name,
                type=normalize_entity_type(item.get("type", "")),
            )
        )

    known_keys = {normalize_entity_key(entity.name) for entity in entities}

    relationships: list[ExtractedRelationship] = []

    for item in payload.get("relationships") or []:

        if not isinstance(item, dict):
            continue

        source = normalize_entity_name(item.get("source", ""))
        target = normalize_entity_name(item.get("target", ""))

        if not source or not target:
            continue

        # Only keep relationships between entities we actually extracted,
        # guarding against the model referencing a name outside the list.
        if normalize_entity_key(source) not in known_keys:
            continue

        if normalize_entity_key(target) not in known_keys:
            continue

        relationships.append(
            ExtractedRelationship(
                source=source,
                relation=normalize_relation_type(item.get("relation", "")),
                target=target,
            )
        )

    return GraphExtractionResult(entities=entities, relationships=relationships)


def extract_graph(text: str) -> GraphExtractionResult:
    """
    Extract entities and relationships from a chunk of text using Gemini.

    Never raises - returns an empty result on any failure (missing API
    key, network/model error, malformed output) so graph enrichment can
    never break document ingestion or query answering.
    """

    text = (text or "").strip()

    if len(text) < MIN_CHUNK_LENGTH:
        return GraphExtractionResult()

    prompt = EXTRACTION_PROMPT.format(
        entity_types=", ".join(SUGGESTED_ENTITY_TYPES),
        text=text,
    )

    try:
        model = get_model()

        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"},
        )

        raw_text = response.text

    except Exception:
        logger.exception("Graph extraction: Gemini call failed")
        return GraphExtractionResult()

    if not raw_text:
        return GraphExtractionResult()

    return _parse_response(raw_text)
