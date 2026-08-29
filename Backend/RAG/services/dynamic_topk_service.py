"""
Dynamic Top-K Retrieval.

Scales retrieval depth to question complexity instead of always
pulling a fixed settings.TOP_K chunks. Deliberately a cheap, local,
dependency-free heuristic - not an LLM call - since retrieval depth is
decided on every single query, and this sprint already adds several
LLM-backed retrieval features (query expansion, HyDE, multi-query)
whose latency/cost shouldn't be compounded by a sizing decision a
simple heuristic handles well enough.
"""

import logging
import re
from typing import Optional

from django.conf import settings

logger = logging.getLogger(__name__)

_CONJUNCTION_RE = re.compile(r"\b(and|or|also|plus|as well as)\b", re.IGNORECASE)

SHORT_QUESTION_WORDS = 6
LONG_QUESTION_WORDS = 15
MULTI_PART_BONUS = 2
LONG_QUESTION_BONUS = 4
MEDIUM_QUESTION_BONUS = 2


def compute_dynamic_top_k(question: str, base_top_k: Optional[int] = None) -> int:
    """
    Return a retrieval depth scaled to the question's apparent
    complexity:
    - short, single-fact questions (<= SHORT_QUESTION_WORDS words)
      keep the base top_k.
    - longer or multi-clause questions retrieve more chunks, up to
      settings.DYNAMIC_TOP_K_MAX.
    - questions with multiple "?" or conjunctions (multi-part
      questions, e.g. "X and also Y?") get an extra bump.

    Always returns at least 1 and never more than
    settings.DYNAMIC_TOP_K_MAX.
    """

    base = base_top_k if base_top_k is not None else settings.TOP_K
    question = (question or "").strip()

    if not question:
        return max(1, base)

    word_count = len(question.split())

    if word_count <= SHORT_QUESTION_WORDS:
        top_k = base
    elif word_count <= LONG_QUESTION_WORDS:
        top_k = base + MEDIUM_QUESTION_BONUS
    else:
        top_k = base + LONG_QUESTION_BONUS

    multi_part = question.count("?") > 1 or bool(_CONJUNCTION_RE.search(question))

    if multi_part:
        top_k += MULTI_PART_BONUS

    top_k = max(1, min(top_k, settings.DYNAMIC_TOP_K_MAX))

    logger.debug(
        "Dynamic top-k: %d word(s), multi_part=%s -> top_k=%d (base=%d)",
        word_count, multi_part, top_k, base,
    )

    return top_k
