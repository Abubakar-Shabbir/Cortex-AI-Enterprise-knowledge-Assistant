"""
Answer-generation prompt templates (Sprint 9).

Centralizes the prompt llm_service.py sends to Gemini and the fixed
"not found" fallback text every consumer of a generated answer needs
to recognize: `query_service.calculate_confidence()` (a hallucination
signal - see below), and `views.search_history` (answered/unanswered
classification). Previously this fallback string was hardcoded
independently in llm_service.py and views.py; CLAUDE.md flagged them
as "keep them in sync if the fallback text ever changes" -
`is_not_found_answer()` is now the one place that check happens.
"""

NOT_FOUND_ANSWER = "I couldn't find the answer in the uploaded document."

# Distinct from NOT_FOUND_ANSWER on purpose: "the sources don't answer
# this" and "the AI service itself is unreachable" are different
# situations that deserve different UI treatment (see
# is_service_unavailable_answer() and ask_ai.html's separate error
# card) - conflating them into one generic fallback message would mean
# a total provider outage looks, to the user, like their documents
# just don't contain the answer.
SERVICE_UNAVAILABLE_ANSWER = "The AI service is temporarily unavailable. Please try again in a moment."


def is_not_found_answer(answer: str) -> bool:
    """
    True if `answer` is (or contains) the fixed fallback sentence
    Gemini is instructed to return verbatim when the sources don't
    answer the question. A substring check, not equality, since even
    a low-temperature model can wrap it in minor whitespace/newline
    variation.
    """

    return bool(answer) and "couldn't find the answer" in answer


def is_service_unavailable_answer(answer: str) -> bool:
    """True if `answer` is the fixed fallback returned when every configured LLM provider failed (see llm_client.AllProvidersFailedError)."""

    return bool(answer) and "temporarily unavailable" in answer


ANSWER_PROMPT_TEMPLATE = """You are a careful, source-grounded AI assistant answering questions about a user's uploaded documents.

Grounding rules:
1. Answer ONLY using the numbered sources below. Never use outside knowledge, even if you are confident it is correct.
2. Every factual claim must be traceable to a source. Cite it inline using its number in square brackets right after the claim, e.g. "The contract renews annually [2]." If multiple sources support one claim, cite all of them, e.g. [1][3].
3. If the sources only partially answer the question, answer what they support and say what is missing - do not fill the gap from your own knowledge.
4. If the sources do not contain the answer at all, reply with exactly this sentence and nothing else:

"{not_found_answer}"

5. Keep the answer clear and concise. Synthesize the sources - do not repeat them verbatim.
6. Answer in the same language the question was asked in, regardless of what language the sources are written in. Do not mix languages within the answer, and do not switch languages partway through.

Sources:
----------------
{context}
----------------

Question:
{question}

Answer:
"""


def build_answer_prompt(context: str, question: str) -> str:
    """
    Fill the answer-generation template. `context` is expected to be
    citation_service.build_cited_context() output - numbered [1]/[2]/
    ... source blocks - so the citation rule above has something
    concrete for the model to point at.

    Used by the streaming path (answer_question_stream()) only - see
    ANSWER_JSON_PROMPT_TEMPLATE/build_structured_answer_prompt() for the
    non-streaming path. Kept as plain prose (not JSON mode) because a
    partial JSON object can't be rendered as live-typed text; see
    query_service.py's module docstring for the full reasoning.
    """

    return ANSWER_PROMPT_TEMPLATE.format(
        not_found_answer=NOT_FOUND_ANSWER,
        context=context,
        question=question,
    )


# JSON-mode counterpart to ANSWER_PROMPT_TEMPLATE (non-streaming path
# only - RAG.services.llm_service.generate_answer()). Same grounding/
# citation rules, extended to ask for a small amount of structure
# (key_points, an optional comparison table) in the same LLM call - the
# same response_format="json" pattern
# RAG.services.ai_tasks_engine_service.py already proved out, reused via
# RAG.services.llm_client.generate_json() rather than a second
# JSON-calling mechanism. "Related Topics" deliberately isn't part of
# this schema - query_service.py derives it from the knowledge graph
# instead, at no extra LLM cost.
ANSWER_JSON_PROMPT_TEMPLATE = """You are a careful, source-grounded AI assistant answering questions about a user's uploaded documents.

Grounding rules:
1. Answer ONLY using the numbered sources below. Never use outside knowledge, even if you are confident it is correct.
2. Every factual claim in "answer" must be traceable to a source. Cite it inline using its number in square brackets right after the claim, e.g. "The contract renews annually [2]." If multiple sources support one claim, cite all of them, e.g. [1][3].
3. If the sources only partially answer the question, answer what they support and say what is missing - do not fill the gap from your own knowledge.
4. If the sources do not contain the answer at all, "answer" must be exactly this sentence and nothing else, and "key_points" must be [] and "table" must be null:

"{not_found_answer}"

5. Keep "answer" clear and concise. Synthesize the sources - do not repeat them verbatim.
6. Write "answer" and "key_points" in the same language the question was asked in, regardless of what language the sources are written in. Do not mix languages within a single field, and do not switch languages partway through.

Respond with ONLY a JSON object, no markdown code fences, no text outside the object, in exactly this shape:
{{
  "answer": "<the cited answer prose, following every rule above>",
  "key_points": ["<short standalone bullet point, still citing its source>", ...],
  "table": {{"headers": ["...", ...], "rows": [["...", ...], ...]}} or null
}}

"key_points": 0 to 5 short bullets pulling out the most important facts already stated in "answer" - each should still carry its citation number. Use [] for a short answer that's already just one or two facts; don't pad for the sake of it.

"table": ONLY a non-null table when the sources contain genuinely comparative or structured data (e.g. multiple items compared across attributes, figures across time periods). Leave it null for a normal narrative answer - do not force a table where it doesn't fit.

Sources:
----------------
{context}
----------------

Question:
{question}
"""


def build_structured_answer_prompt(context: str, question: str) -> str:
    """JSON-mode counterpart to build_answer_prompt() - see ANSWER_JSON_PROMPT_TEMPLATE."""

    return ANSWER_JSON_PROMPT_TEMPLATE.format(
        not_found_answer=NOT_FOUND_ANSWER,
        context=context,
        question=question,
    )
