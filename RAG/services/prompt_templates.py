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


def is_not_found_answer(answer: str) -> bool:
    """
    True if `answer` is (or contains) the fixed fallback sentence
    Gemini is instructed to return verbatim when the sources don't
    answer the question. A substring check, not equality, since even
    a low-temperature model can wrap it in minor whitespace/newline
    variation.
    """

    return bool(answer) and "couldn't find the answer" in answer


ANSWER_PROMPT_TEMPLATE = """You are a careful, source-grounded AI assistant answering questions about a user's uploaded documents.

Grounding rules:
1. Answer ONLY using the numbered sources below. Never use outside knowledge, even if you are confident it is correct.
2. Every factual claim must be traceable to a source. Cite it inline using its number in square brackets right after the claim, e.g. "The contract renews annually [2]." If multiple sources support one claim, cite all of them, e.g. [1][3].
3. If the sources only partially answer the question, answer what they support and say what is missing - do not fill the gap from your own knowledge.
4. If the sources do not contain the answer at all, reply with exactly this sentence and nothing else:

"{not_found_answer}"

5. Keep the answer clear and concise. Synthesize the sources - do not repeat them verbatim.

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
    """

    return ANSWER_PROMPT_TEMPLATE.format(
        not_found_answer=NOT_FOUND_ANSWER,
        context=context,
        question=question,
    )
