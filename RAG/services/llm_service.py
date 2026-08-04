import logging

from django.conf import settings

from .gemini_client import get_model
from .prompt_templates import NOT_FOUND_ANSWER, build_answer_prompt

logger = logging.getLogger(__name__)


def generate_answer(context, question):
    """
    Generate a grounded, cited answer to `question` from `context`.

    `context` is expected to already be
    citation_service.build_cited_context() output - numbered source
    blocks the prompt (prompt_templates.build_answer_prompt()) asks
    Gemini to cite by number, e.g. "[1]". Uses
    gemini_client.get_model() (settings.LLM_MODEL) rather than
    configuring genai directly, so this module no longer duplicates
    that configuration logic - see gemini_client.py.

    settings.ANSWER_TEMPERATURE runs generation at a low sampling
    temperature by default, so the model favors sticking to the cited
    sources over improvising - a hallucination-reduction lever
    alongside the prompt's grounding rules.
    """

    try:

        model = get_model()

        prompt = build_answer_prompt(context, question)

        response = model.generate_content(
            prompt,
            generation_config={"temperature": settings.ANSWER_TEMPERATURE},
        )

        if response.text:

            return response.text.strip()

        else:

            return NOT_FOUND_ANSWER

    except Exception as e:
        logger.exception("Gemini answer generation failed")

        return f"Gemini Error: {e}"
