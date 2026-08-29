"""
Shared LLM-backed query rewriting service.

This module generates multiple semantically equivalent versions of a
user query to improve retrieval quality.

The generated query variants are reused by:

- Query Expansion
- Multi Query Retrieval (RAG Fusion)

The service is provider-independent and works with any configured LLM
through llm_client.py (Gemini/OpenRouter).

It never raises exceptions.
If generation fails, the original question is returned.
"""

import json
import logging
import re

from .llm_client import get_llm

logger = logging.getLogger(__name__)


# ============================================================
# Configuration
# ============================================================

DEFAULT_NUM_VARIANTS = 3
MIN_QUESTION_LENGTH = 6


# ============================================================
# Prompt
# ============================================================

VARIANT_PROMPT = """
You are an enterprise search query rewriting engine.

Your task is to generate alternate versions of a user's search query.

Requirements

- Preserve the original meaning exactly.
- Do NOT answer the question.
- Use different wording, synonyms and phrasing.
- Produce diverse search-friendly variations.
- Return JSON only.

JSON Format

{{
    "variants": [
        "...",
        "...",
        "..."
    ]
}}

Generate {num_variants} alternate queries.

Question

{question}
"""


# ============================================================
# Helpers
# ============================================================

def _normalize(text: str) -> str:
    """Normalize whitespace."""
    return re.sub(r"\s+", " ", (text or "")).strip()


def _extract_json(text: str) -> str:
    """
    Extract JSON block from LLM response.
    Handles markdown code blocks automatically.
    """

    if not text:
        return ""

    text = text.strip()

    if text.startswith("```"):

        text = re.sub(r"^```(?:json)?", "", text)
        text = re.sub(r"```$", "", text)

    return text.strip()


def _parse_response(
    raw_text: str,
    question: str,
) -> list[str]:
    """
    Parse LLM JSON response.

    Always returns at least the original question.
    """

    raw_text = _extract_json(raw_text)

    try:
        payload = json.loads(raw_text)

    except Exception:

        logger.warning("Unable to parse query variants JSON.")

        return [question]

    variants = []

    if isinstance(payload, dict):

        for item in payload.get("variants", []):

            if not isinstance(item, str):
                continue

            item = _normalize(item)

            if item:
                variants.append(item)

    if not variants:
        return [question]

    seen = set()

    results = []

    for item in [question] + variants:

        key = item.lower()

        if key in seen:
            continue

        seen.add(key)

        results.append(item)

    return results


# ============================================================
# Public API
# ============================================================

def generate_query_variants(
    question: str,
    num_variants: int = DEFAULT_NUM_VARIANTS,
) -> list[str]:
    """
    Generate multiple search query variants.

    Returns

        [
            original_query,
            variant_1,
            variant_2,
            ...
        ]

    Never raises.
    """

    question = _normalize(question)

    if not question:
        return []

    if len(question) < MIN_QUESTION_LENGTH:
        return [question]

    prompt = VARIANT_PROMPT.format(
        question=question,
        num_variants=num_variants,
    )

    try:

        llm = get_llm()

        response = llm.generate(prompt)

        if not response:
            return [question]

        return _parse_response(
            response,
            question,
        )

    except Exception:

        logger.exception(
            "Query variant generation failed."
        )

        return [question]