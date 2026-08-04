"""
Source citation formatting/extraction (Sprint 9).

Builds the numbered source blocks the answer prompt asks Gemini to
cite by number (build_cited_context()) and, symmetrically, parses
which of those numbers actually appear in the generated answer
(extract_citations()) - turning free-text "[n]" markers back into
structured source references the UI can render and
calculate_confidence() can use as a groundedness signal.
"""

import re
from typing import Any

CITATION_PATTERN = re.compile(r"\[(\d+)\]")


def build_cited_context(chunks: list[dict[str, Any]]) -> str:
    """
    Number `chunks` 1..N, in the order retrieve_chunks() /
    compress_context() returned them, and render each as a labeled
    block the answer prompt can cite by number. This numbering is the
    single source of truth extract_citations() maps back against -
    callers must not reorder `chunks` between the two calls.
    """

    blocks = []

    for index, chunk in enumerate(chunks, start=1):

        blocks.append(
            f"[{index}] ({chunk['document']}, chunk {chunk['chunk_number']}):\n{chunk['content']}"
        )

    return "\n\n".join(blocks)


def extract_citations(answer: str, chunks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Parse "[n]" markers out of `answer` and return the subset of
    `chunks` they reference, in citation order. Each matching chunk
    dict is annotated in place with a `citation_number` key, for
    template display (`ask_ai.html` marks cited source cards) - the
    same "enrich the chunk dict as it flows through the pipeline"
    pattern reranker_service.py already uses for `rerank_score`, safe
    here since nothing else holds a pre-citation reference to these
    dicts.

    Out-of-range numbers (a citation number the model invented, beyond
    len(chunks)) are silently dropped rather than raising, since a
    malformed citation is a generation quirk, not a reason to fail the
    whole answer.
    """

    if not answer or not chunks:
        return []

    seen_numbers = []

    for match in CITATION_PATTERN.finditer(answer):

        number = int(match.group(1))

        if 1 <= number <= len(chunks) and number not in seen_numbers:
            seen_numbers.append(number)

    citations = []

    for number in sorted(seen_numbers):

        chunk = chunks[number - 1]
        chunk["citation_number"] = number
        citations.append(chunk)

    return citations
