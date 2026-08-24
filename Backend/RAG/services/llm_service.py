"""
LLM Service

Handles answer generation using the configured LLM provider.

This module is provider-agnostic and communicates only with the
central LLM client (llm_client.py), which is responsible for
selecting the configured provider, automatic multi-provider fallback
(OpenRouter -> Groq -> Gemini, or whichever order the primary provider
implies), retries, and typed errors.

Responsibilities
----------------
- Build the grounded, structured (JSON-mode) RAG prompt - same
  response_format="json" pattern ai_tasks_engine_service.py already
  proved out, via llm_client.parse_json_response() for the shared
  parse/validate step.
- Send it to the configured LLM
- Return the generated answer plus its structured extras (key points,
  an optional comparison table)
- Handle failures gracefully - distinguishing "the sources don't
  answer this" (NOT_FOUND_ANSWER) from "every LLM provider failed"
  (SERVICE_UNAVAILABLE_ANSWER), so the UI can show the right message
  for each instead of one generic fallback.
"""

import logging

from django.conf import settings

from .llm_client import AllProvidersFailedError, get_llm, parse_json_response
from .prompt_templates import (
    build_structured_answer_prompt,
    NOT_FOUND_ANSWER,
    SERVICE_UNAVAILABLE_ANSWER,
)

logger = logging.getLogger(__name__)


def generate_answer(context: str, question: str) -> tuple[str, dict]:
    """
    Generate a grounded, structured answer using retrieved context.

    Parameters
    ----------
    context : str
        Context produced by the retrieval pipeline.
        Usually output from citation_service.build_cited_context().

    question : str
        User's question.

    Returns
    -------
    (answer, extras) : tuple[str, dict]
        `answer` is grounded prose with "[n]" citations - NOT_FOUND_ANSWER
        if the model determined the sources don't answer the question, or
        SERVICE_UNAVAILABLE_ANSWER if every configured LLM provider
        failed. `extras` is {"key_points": list[str], "table": dict|None}
        - always {} (no extras) alongside either fallback answer, since
        there's nothing to structure when there's no real answer.
    """

    try:

        prompt = build_structured_answer_prompt(
            context=context,
            question=question,
        )

        # Fetched fresh on every call (not cached at module import) so
        # a provider/model change saved from Admin > Settings takes
        # effect immediately - see llm_client.py's module docstring.
        llm = get_llm()

        raw = llm.generate(
            prompt,
            temperature=settings.ANSWER_TEMPERATURE,
            response_format="json",
            max_tokens=settings.ANSWER_MAX_TOKENS,
        )

        parsed = parse_json_response(raw)

        if parsed is None:
            logger.warning("LLM answer generation: empty/invalid/non-object JSON response.")
            return NOT_FOUND_ANSWER, {}

        answer = (parsed.get("answer") or "").strip()

        if not answer:
            return NOT_FOUND_ANSWER, {}

        extras = {
            "key_points": parsed.get("key_points") or [],
            "table": parsed.get("table") or None,
        }

        return answer, extras

    except AllProvidersFailedError:

        logger.exception("LLM answer generation failed - every configured provider failed.")

        return SERVICE_UNAVAILABLE_ANSWER, {}

    except Exception:

        logger.exception("LLM answer generation failed.")

        return NOT_FOUND_ANSWER, {}
