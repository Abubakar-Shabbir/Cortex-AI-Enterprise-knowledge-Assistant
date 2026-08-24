"""
HyDE (Hypothetical Document Embeddings).

Instead of embedding the user's short question directly, HyDE asks the
configured LLM to generate a short hypothetical document. That document
is embedded and used for vector search to improve semantic retrieval.
"""

import logging

from .llm_client import get_llm

logger = logging.getLogger(__name__)

MIN_QUESTION_LENGTH = 6
MAX_HYPOTHETICAL_CHARS = 1500

HYDE_PROMPT = """
Write a short, plausible passage (2-4 sentences) that would answer the
following question as if it were extracted from a real document.

Rules:
- Return only the passage.
- No headings.
- No markdown.
- Keep it concise.
- It is acceptable to invent facts because this text is only used for
semantic retrieval.

Question:
----------------
{question}
----------------
"""


def generate_hypothetical_document(question: str) -> str:
    """
    Generate a hypothetical document for HyDE retrieval.

    Returns an empty string on failure.
    """

    question = (question or "").strip()

    if len(question) < MIN_QUESTION_LENGTH:
        return ""

    try:
        llm = get_llm()

        passage = llm.generate(
            HYDE_PROMPT.format(question=question)
        ).strip()

    except Exception:
        logger.exception("HyDE generation failed")
        return ""

    return passage[:MAX_HYPOTHETICAL_CHARS]