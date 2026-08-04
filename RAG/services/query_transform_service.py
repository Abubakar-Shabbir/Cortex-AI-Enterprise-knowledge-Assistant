"""
Shared LLM-backed query rewriting primitive.

generate_query_variants() is the single place that asks Gemini for
alternate phrasings of a question. It's reused by two different
Sprint 6 features rather than each having its own prompt/parsing
logic:

- query_expansion_service.expand_query() folds the variants' distinct
  wording into one enriched query string for a single lexical search.
- multi_query_service.multi_query_search() runs a separate retrieval
  pass per variant and fuses the ranked results (RAG-Fusion style).

Never raises - any failure (missing API key, network error, malformed
JSON) falls back to [question], so callers always get at least the
original question back.
"""

import json
import logging
import re

from .gemini_client import get_model

logger = logging.getLogger(__name__)

DEFAULT_NUM_VARIANTS = 3
MIN_QUESTION_LENGTH = 6

VARIANT_PROMPT = """You are a search query rewriting engine for a document
retrieval system.

Given the user's question, write {num_variants} alternate ways to ask it -
using different wording, synonyms, or phrasing - so a keyword and semantic
search over document text is more likely to find relevant passages.

Rules:
- Preserve the original meaning and intent exactly. Do not answer the
  question, and do not introduce new facts or assumptions.
- Each variant should be a full, standalone question or search phrase.
- Make the variants genuinely different from each other, not trivial
  rewordings.
- Respond with JSON only, matching this shape exactly:
{{"variants": ["...", "...", "..."]}}

Question:
----------------
{question}
----------------
"""


def _normalize_variant(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def _parse_variants(raw_text: str, question: str) -> list[str]:

    try:
        payload = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        logger.warning("Query transform: could not parse LLM JSON output: %s", exc)
        return [question]

    if not isinstance(payload, dict):
        return [question]

    variants = [
        _normalize_variant(item)
        for item in (payload.get("variants") or [])
        if isinstance(item, str) and _normalize_variant(item)
    ]

    if not variants:
        return [question]

    # De-duplicate case-insensitively while preserving order, and make
    # sure the original question is always included as the first entry
    # so downstream callers can rely on variants[0] == question.
    seen = {question.lower().strip()}
    deduped = [question]

    for variant in variants:
        key = variant.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(variant)

    return deduped


def generate_query_variants(
    question: str,
    num_variants: int = DEFAULT_NUM_VARIANTS,
) -> list[str]:
    """
    Return [question, variant_1, variant_2, ...] - the original
    question first, followed by up to `num_variants` LLM-generated
    alternate phrasings. Falls back to [question] on any failure.
    """

    question = (question or "").strip()

    if len(question) < MIN_QUESTION_LENGTH:
        return [question] if question else []

    try:
        model = get_model()

        response = model.generate_content(
            VARIANT_PROMPT.format(num_variants=num_variants, question=question),
            generation_config={"response_mime_type": "application/json"},
        )

        raw_text = response.text

    except Exception:
        logger.exception("Query transform: Gemini call failed")
        return [question]

    if not raw_text:
        return [question]

    return _parse_variants(raw_text, question)
