"""
graph_extraction_service.py

Enterprise Knowledge Graph Extraction Service

This module extracts entities and relationships from document chunks
using the configured LLM provider.

Supported providers are abstracted behind llm_client.py, therefore
this module never communicates directly with Gemini, OpenRouter,
OpenAI, Claude, or any other model.

Responsibilities
----------------
- Build extraction prompt
- Call the configured LLM
- Parse JSON
- Validate entities
- Validate relationships
- Never break document ingestion
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from .llm_client import get_llm

logger = logging.getLogger(__name__)

DEFAULT_ENTITY_TYPE = "MISC"
DEFAULT_RELATION_TYPE = "RELATED_TO"

MIN_CHUNK_LENGTH = 20

SUPPORTED_ENTITY_TYPES = (
    "PERSON",
    "ORGANIZATION",
    "LOCATION",
    "DATE",
    "PRODUCT",
    "EVENT",
    "MISC",
)

EXTRACTION_PROMPT = """
You are an expert Knowledge Graph extraction engine.

Your task is to extract:

1. Named Entities
2. Relationships between entities

Rules

• Extract ONLY information explicitly present.
• Never hallucinate.
• Reuse identical entity names.
• Use concise relation labels.
• If no entities exist return empty arrays.

Return ONLY valid JSON.

Schema:

{{
  "entities":[
      {{
          "name":"",
          "type":""
      }}
  ],

  "relationships":[
      {{
          "source":"",
          "relation":"",
          "target":""
      }}
  ]
}}

Supported entity types:

{entity_types}

Text

----------------------
{text}
----------------------
"""


@dataclass(slots=True)
class ExtractedEntity:
    name: str
    type: str = DEFAULT_ENTITY_TYPE


@dataclass(slots=True)
class ExtractedRelationship:
    source: str
    relation: str
    target: str


@dataclass(slots=True)
class GraphExtractionResult:
    entities: list[ExtractedEntity] = field(default_factory=list)
    relationships: list[ExtractedRelationship] = field(default_factory=list)


def normalize_entity_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "")).strip()


def normalize_entity_key(name: str) -> str:
    return normalize_entity_name(name).lower()


def normalize_entity_type(entity_type: str) -> str:

    cleaned = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        (entity_type or "").strip(),
    )

    cleaned = cleaned.strip("_").upper()

    return cleaned or DEFAULT_ENTITY_TYPE


def normalize_relation_type(relation: str) -> str:

    cleaned = re.sub(
        r"[^A-Za-z0-9]+",
        "_",
        (relation or "").strip(),
    )

    cleaned = cleaned.strip("_").upper()

    return cleaned or DEFAULT_RELATION_TYPE


def _parse_response(raw_text: str) -> GraphExtractionResult:

    try:

        payload = json.loads(raw_text)

    except Exception:

        logger.warning("Invalid JSON returned by LLM.")

        return GraphExtractionResult()

    if not isinstance(payload, dict):

        return GraphExtractionResult()

    entities = []

    seen = set()

    for item in payload.get("entities", []):

        if not isinstance(item, dict):
            continue

        name = normalize_entity_name(item.get("name"))

        if not name:
            continue

        key = normalize_entity_key(name)

        if key in seen:
            continue

        seen.add(key)

        entities.append(
            ExtractedEntity(
                name=name,
                type=normalize_entity_type(
                    item.get("type")
                ),
            )
        )

    entity_keys = {
        normalize_entity_key(e.name)
        for e in entities
    }

    relationships = []

    for item in payload.get("relationships", []):

        if not isinstance(item, dict):
            continue

        source = normalize_entity_name(
            item.get("source")
        )

        relation = normalize_relation_type(
            item.get("relation")
        )

        target = normalize_entity_name(
            item.get("target")
        )

        if not source or not target:
            continue

        if normalize_entity_key(source) not in entity_keys:
            continue

        if normalize_entity_key(target) not in entity_keys:
            continue

        relationships.append(

            ExtractedRelationship(
                source=source,
                relation=relation,
                target=target,
            )

        )

    return GraphExtractionResult(
        entities=entities,
        relationships=relationships,
    )


def extract_graph(text: str) -> GraphExtractionResult:
    """
    Extract Knowledge Graph from text.

    Never raises exceptions.

    Returns
    -------
    GraphExtractionResult
    """

    text = (text or "").strip()

    if len(text) < MIN_CHUNK_LENGTH:

        return GraphExtractionResult()

    prompt = EXTRACTION_PROMPT.format(

        entity_types=", ".join(
            SUPPORTED_ENTITY_TYPES
        ),

        text=text,

    )

    try:

        # Fetched fresh on every call (not cached at module import) so
        # a provider/model change saved from Admin > Settings takes
        # effect immediately - see llm_client.py's module docstring.
        llm = get_llm()

        raw_response = llm.generate(

            prompt=prompt,

            temperature=0.0,

            response_format="json",

        )

    except Exception:

        logger.exception(
            "Knowledge graph extraction failed."
        )

        return GraphExtractionResult()

    if not raw_response:

        return GraphExtractionResult()

    return _parse_response(raw_response)