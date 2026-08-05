"""
Central LLM Client

Provides a single interface for interacting with any supported
Large Language Model provider.

Supported Providers
-------------------
- Gemini
- OpenRouter

Features
--------
- Automatic provider selection
- Automatic fallback
- Enterprise ready
"""

import logging
import requests

import google.generativeai as genai

from django.conf import settings

logger = logging.getLogger(__name__)


# ============================================================
# Base Class
# ============================================================

class BaseLLMClient:
    """Base interface for every LLM provider."""

    def generate(self, prompt: str) -> str:
        raise NotImplementedError


# ============================================================
# Gemini Client
# ============================================================

class GeminiClient(BaseLLMClient):

    def __init__(self):

        genai.configure(
            api_key=settings.GEMINI_API_KEY
        )

        self.model = genai.GenerativeModel(
            settings.LLM_MODEL
        )

    def generate(self, prompt: str) -> str:

        response = self.model.generate_content(prompt)

        return response.text.strip()


# ============================================================
# OpenRouter Client
# ============================================================

class OpenRouterClient(BaseLLMClient):

    API_URL = "https://openrouter.ai/api/v1/chat/completions"

    def generate(self, prompt: str) -> str:

        headers = {
            "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": getattr(settings, "SITE_URL", ""),
            "X-Title": getattr(settings, "SITE_NAME", "RAG Assistant"),
        }

        payload = {
            "model": settings.OPENROUTER_MODEL,
            "messages": [
                {
                    "role": "user",
                    "content": prompt,
                }
            ],
            "temperature": 0.2,
        }

        response = requests.post(
            self.API_URL,
            headers=headers,
            json=payload,
            timeout=120,
        )

        response.raise_for_status()

        data = response.json()

        return data["choices"][0]["message"]["content"].strip()


# ============================================================
# Factory
# ============================================================

def _get_primary_client() -> BaseLLMClient:

    provider = settings.LLM_PROVIDER.lower()

    if provider == "gemini":
        return GeminiClient()

    if provider == "openrouter":
        return OpenRouterClient()

    raise ValueError(
        f"Unsupported LLM Provider: {provider}"
    )


# ============================================================
# Public Client
# ============================================================

class LLMClient:
    """
    Enterprise wrapper.

    Uses configured provider.

    Automatically falls back to OpenRouter
    if Gemini fails.
    """

    def __init__(self):

        self.client = _get_primary_client()

    def generate(self, prompt: str) -> str:

        try:

            return self.client.generate(prompt)

        except Exception as exc:

            logger.exception("Primary LLM failed.")

            if settings.LLM_PROVIDER.lower() == "gemini":

                logger.info(
                    "Switching to OpenRouter fallback..."
                )

                return OpenRouterClient().generate(prompt)

            raise exc


# ============================================================
# Singleton Factory
# ============================================================

_client = None


def get_llm() -> LLMClient:

    global _client

    if _client is None:

        _client = LLMClient()

    return _client