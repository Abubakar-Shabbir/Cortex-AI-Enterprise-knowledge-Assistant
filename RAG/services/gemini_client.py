"""
Shared Gemini configuration and model factory.

llm_service.py keeps its own inline genai.configure()/GenerativeModel()
call untouched (hardcoded to "gemini-2.0-flash") to avoid changing its
existing, already-relied-upon behavior. This module exists so new
Gemini-backed services - starting with graph_extraction_service.py -
don't duplicate that configuration logic.
"""

import logging

import google.generativeai as genai
from django.conf import settings

logger = logging.getLogger(__name__)

_configured = False


def _ensure_configured() -> None:
    global _configured

    if not _configured:
        genai.configure(api_key=settings.GEMINI_API_KEY)
        _configured = True


def get_model(model_name: str | None = None) -> genai.GenerativeModel:
    """
    Return a configured Gemini model instance.
    Defaults to settings.LLM_MODEL when no name is given.
    """

    _ensure_configured()

    return genai.GenerativeModel(model_name or settings.LLM_MODEL)
