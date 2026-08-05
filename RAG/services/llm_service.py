"""
LLM Service

Handles answer generation using the configured LLM provider.

This module is provider-agnostic and communicates only with the
central LLM client. The client is responsible for:

- Selecting the configured provider
- Automatic Gemini -> OpenRouter fallback
- Future provider support (OpenAI, Claude, DeepSeek, etc.)

Responsibilities
----------------
- Build the grounded RAG prompt
- Send it to the configured LLM
- Return the generated answer
- Handle failures gracefully
"""

import logging

from .llm_client import get_llm
from .prompt_templates import (
    build_answer_prompt,
    NOT_FOUND_ANSWER,
)

logger = logging.getLogger(__name__)

# Singleton client
llm = get_llm()


def generate_answer(context: str, question: str) -> str:
    """
    Generate a grounded answer using retrieved context.

    Parameters
    ----------
    context : str
        Context produced by the retrieval pipeline.
        Usually output from citation_service.build_cited_context().

    question : str
        User's question.

    Returns
    -------
    str
        Grounded answer with citations.
    """

    try:

        prompt = build_answer_prompt(
            context=context,
            question=question,
        )

        answer = llm.generate(prompt)

        if not answer:
            return NOT_FOUND_ANSWER

        return answer.strip()

    except Exception:

        logger.exception("LLM answer generation failed.")

        return NOT_FOUND_ANSWER