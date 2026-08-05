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

    Uses the configured primary provider and automatically falls back
    to the other supported provider if the primary call fails (e.g.
    Gemini quota exhaustion, or an OpenRouter outage).
    """

    def __init__(self):

        self.primary_provider = settings.LLM_PROVIDER.lower()
        self.client = _get_primary_client()

    def generate(self, prompt: str) -> str:

        try:

            return self.client.generate(prompt)

        except Exception as exc:

            logger.exception(
                "Primary LLM (%s) failed.", self.primary_provider
            )

            fallback_provider = (
                "openrouter" if self.primary_provider == "gemini" else "gemini"
            )

            logger.info(
                "Switching to %s fallback...", fallback_provider
            )

            try:

                if fallback_provider == "gemini":
                    return GeminiClient().generate(prompt)

                return OpenRouterClient().generate(prompt)

            except Exception:

                logger.exception(
                    "Fallback LLM (%s) also failed.", fallback_provider
                )

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


def reset_llm_client():
    """
    Clear the cached LLMClient singleton. Needed because LLMClient
    reads settings.LLM_PROVIDER once, at construction - unlike every
    other RAG service, which re-reads its settings.X value fresh on
    every call, so a live SystemConfiguration change is invisible to
    it until this is called. Called by
    system_config_service.save_config() whenever an admin saves the
    Settings page.
    """

    global _client
    _client = None