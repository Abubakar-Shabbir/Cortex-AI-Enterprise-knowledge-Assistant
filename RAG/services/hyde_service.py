"""
HyDE (Hypothetical Document Embeddings).

Instead of embedding the user's short question directly, HyDE asks the
LLM to write a short hypothetical passage that would plausibly answer
it, then embeds *that* passage for the vector similarity search. A
generated passage tends to be closer, in the embedding space, to real
document prose than a terse question is - improving recall for
semantic search.

Reference: Gao et al., "Precise Zero-Shot Dense Retrieval without
Relevance Labels" (2022).
"""

import logging

from .gemini_client import get_model

logger = logging.getLogger(__name__)

MIN_QUESTION_LENGTH = 6
MAX_HYPOTHETICAL_CHARS = 1500

HYDE_PROMPT = """Write a short, plausible passage (2-4 sentences) that
would answer the following question, as if it were an excerpt from a
real document on the subject.

Rules:
- Write only the passage itself - no preamble, no "Here is a passage",
  no headings.
- It's fine if the specific facts are made up - this passage is only
  used to find real documents with similar wording, it is never shown
  to the user or treated as a real answer.
- Keep it concise and on-topic.

Question:
----------------
{question}
----------------
"""


def generate_hypothetical_document(question: str) -> str:
    """
    Return a short hypothetical passage answering `question`, or an
    empty string on any failure (missing API key, network/model
    error, empty response). Never raises - callers should treat an
    empty result as "HyDE unavailable, fall back to normal search".
    """

    question = (question or "").strip()

    if len(question) < MIN_QUESTION_LENGTH:
        return ""

    try:
        model = get_model()

        response = model.generate_content(
            HYDE_PROMPT.format(question=question),
        )

        passage = (response.text or "").strip()

    except Exception:
        logger.exception("HyDE: Gemini call failed")
        return ""

    return passage[:MAX_HYPOTHETICAL_CHARS]
