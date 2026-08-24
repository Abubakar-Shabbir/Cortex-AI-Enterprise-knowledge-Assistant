"""
Query Expansion.

Enriches a question with additional related terms drawn from LLM-
generated alternate phrasings (query_transform_service), producing a
single, richer string for lexical (BM25) search.

Vector search intentionally keeps using the original question rather
than the expanded string - embedding a keyword-stuffed sentence isn't
more semantically accurate, only lexical/keyword matching benefits
from the extra terms.
"""

import logging
import re

from .query_transform_service import generate_query_variants

logger = logging.getLogger(__name__)

DEFAULT_NUM_VARIANTS = 3
MAX_EXTRA_TERMS = 12

_WORD_RE = re.compile(r"[A-Za-z0-9]+")


def _tokenize(text: str) -> set[str]:
    return {match.group(0).lower() for match in _WORD_RE.finditer(text or "")}


def expand_query(question: str, num_variants: int = DEFAULT_NUM_VARIANTS) -> str:
    """
    Build a lexically-enriched version of `question` for BM25 search:
    the original question plus distinct terms drawn from LLM-generated
    alternate phrasings.

    Never raises, and falls back to the original question unchanged if
    expansion fails or adds nothing new - so a caller can always treat
    the return value as a safe drop-in replacement for `question`.
    """

    question = (question or "").strip()

    if not question:
        return question

    try:
        variants = generate_query_variants(question, num_variants=num_variants)
    except Exception:
        logger.exception("Query expansion failed for question: %r", question)
        return question

    original_terms = _tokenize(question)
    seen = set(original_terms)
    extra_terms: list[str] = []

    for variant in variants[1:]:
        for term in _tokenize(variant):
            if term not in seen:
                seen.add(term)
                extra_terms.append(term)

    if not extra_terms:
        return question

    expanded = question + " " + " ".join(extra_terms[:MAX_EXTRA_TERMS])

    logger.info(
        "Query expansion: added %d term(s) to question %r",
        min(len(extra_terms), MAX_EXTRA_TERMS), question,
    )

    return expanded
