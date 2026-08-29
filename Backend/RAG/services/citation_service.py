"""
Source citation formatting/extraction (Sprint 9).

Builds the numbered source blocks the answer prompt asks Gemini to
cite by number (build_cited_context()) and, symmetrically, parses
which of those numbers actually appear in the generated answer
(extract_citations()) - turning free-text "[n]" markers back into
structured source references the UI can render and
calculate_confidence() can use as a groundedness signal.
"""

import logging
import re
from typing import Any

import markdown
import nh3
from django.conf import settings
from django.utils.safestring import mark_safe

logger = logging.getLogger(__name__)

CITATION_PATTERN = re.compile(r"\[(\d+)\]")

# Instruction-tuned models default to Markdown (bold, headers, bullet/
# numbered lists, fenced code) unless told otherwise - the answer
# prompts (prompt_templates.py) don't forbid it, and "advanced"
# structured answers make it more likely, not less. render_answer_html()
# below renders that Markdown to real HTML instead of showing the raw
# "**bold**"/"```code```" syntax as literal text, which is what a plain
# escape()-only render (the previous implementation) does.
#
# Tag/attribute allowlist for nh3.clean() after Markdown conversion:
# Python-Markdown passes raw HTML embedded in its input straight
# through unchanged (a documented behavior, not a bug), so the
# Markdown output itself is NOT safe to mark_safe() directly - it must
# be sanitized. This allowlist covers everything the "fenced_code" /
# "tables" / "sane_lists" extensions below can produce, nothing more -
# in particular no <script>/<style>/on*= handlers, and no <a> (the
# model has no legitimate reason to emit links from document content;
# citations are the one linking mechanism this page uses, and those are
# rendered as buttons by the citation-marker substitution below, not by
# Markdown).
_ALLOWED_TAGS = {
    "p", "br", "strong", "b", "em", "i", "del", "code", "pre",
    "ul", "ol", "li", "blockquote", "hr",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td",
}


def _markdown_to_safe_html(text: str) -> str:
    """Markdown source -> sanitized HTML fragment (not yet mark_safe'd - render_answer_html() still needs to substitute citation markers into the result first)."""

    html = markdown.markdown(
        text or "",
        extensions=["fenced_code", "tables", "sane_lists", "nl2br"],
    )

    return nh3.clean(html, tags=_ALLOWED_TAGS, attributes={})

# The clickable citation marker ask_ai.html's Alpine component hooks
# via @click - scrollToSource() (defined in the template) scrolls to
# and briefly highlights the matching source card below the answer.
_CITATION_MARKER_HTML = (
    '<button type="button" @click="scrollToSource({0})" '
    'class="mx-0.5 inline-flex h-[18px] min-w-[18px] items-center justify-center rounded '
    'bg-primary/15 px-1 align-text-top text-[10px] font-semibold text-primary '
    'transition-colors hover:bg-primary/25 dark:bg-primary-soft/20 dark:text-primary-soft">'
    "{0}</button>"
)


def build_cited_context(chunks: list[dict[str, Any]], max_chars: int = None) -> str:
    """
    Number `chunks` 1..N, in the order retrieve_chunks() /
    compress_context() returned them, and render each as a labeled
    block the answer prompt can cite by number. This numbering is the
    single source of truth extract_citations() maps back against -
    callers must not reorder `chunks` between the two calls.

    `max_chars` (default settings.MAX_CONTEXT_CHARS) is a defensive
    cap, not a normal code path - at today's chunk/top-k sizing the
    context never gets close to it. If it would be exceeded, trailing
    whole blocks are dropped (never mid-block truncated, so a source
    the model does cite is always intact) - the skipped chunks simply
    never appear in `answer`'s "[n]" markers, since extract_citations()
    only recognizes numbers the model actually saw and used.
    """

    if max_chars is None:
        max_chars = settings.MAX_CONTEXT_CHARS

    blocks = []
    total_chars = 0
    dropped = 0

    for index, chunk in enumerate(chunks, start=1):

        block = f"[{index}] ({chunk['document']}, chunk {chunk['chunk_number']}):\n{chunk['content']}"
        block_chars = len(block) + (2 if blocks else 0)  # + the "\n\n" join separator

        if blocks and total_chars + block_chars > max_chars:
            dropped = len(chunks) - len(blocks)
            break

        blocks.append(block)
        total_chars += block_chars

    if dropped:
        logger.warning(
            "build_cited_context: dropped %d trailing chunk(s) - context would have exceeded MAX_CONTEXT_CHARS=%d",
            dropped, max_chars,
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


def render_answer_html(answer: str):
    """
    Renders `answer` (Markdown, possibly containing "[n]" citation
    markers) to sanitized HTML with every citation turned into a
    clickable button, for ask_ai.html to render as {{ result.answer_html }}
    (already mark_safe'd - no |safe needed, and none should be added
    elsewhere in the chain).

    Markdown conversion + nh3 sanitization (_markdown_to_safe_html())
    happens first, over the *entire* answer, before citation markers are
    substituted back in as raw HTML - so nothing in the LLM's own
    output, including a citation number itself, can smuggle unsanitized
    markup into the page. nh3 only allows a fixed, safe tag set (see
    _ALLOWED_TAGS) - no <script>, no event-handler attributes, no <a>.
    """

    safe_html = _markdown_to_safe_html(answer)

    linked = CITATION_PATTERN.sub(
        lambda match: _CITATION_MARKER_HTML.format(match.group(1)),
        safe_html,
    )

    return mark_safe(linked)
