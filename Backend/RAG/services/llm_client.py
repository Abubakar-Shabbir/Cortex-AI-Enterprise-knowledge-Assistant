"""
Central LLM Client

A single interface every RAG.services module goes through to talk to
an LLM, regardless of provider - never call google.genai or
requests.post(openrouter/groq URL) anywhere outside this file.

Supported Providers
--------------------
- OpenRouter (default primary - free-tier model, see PROVIDER_REGISTRY)
- Groq
- Gemini

Architecture
------------
Adapter/factory pattern: every provider is a small BaseLLMClient
subclass registered in PROVIDER_REGISTRY (label, client class, which
settings.py attributes hold its API key/model, and a curated list of
known-good free models for the Settings UI). Adding a 4th provider
later is one new class + one registry entry - nothing else in the app
(the fallback chain, the Settings UI, the health-check endpoint) has
any provider-specific code to touch.

LLMClient (returned by get_llm()) is a stateless wrapper around that
registry: every generate()/generate_stream() call re-reads
settings.LLM_PROVIDER and the relevant model setting fresh, builds a
fallback chain (primary first, then the rest of FALLBACK_PRIORITY that
have an API key configured), and walks it with per-provider retries,
typed-exception-based routing (an auth failure skips straight to the
next provider instead of retrying a key that will never start
working), and structured logging of every attempt.

Being stateless here is deliberate, not incidental: the long-lived
process-wide singleton (get_llm()) never caches which provider/model
it was built with, so a Settings-page change is picked up by every
caller - existing or future - on its very next call, with no
"remember to re-fetch get_llm() inside the function, not at module
level" convention required anywhere else in the codebase.
"""

import json
import logging
import time
from contextvars import ContextVar
from typing import Iterator, Optional

import httpx
import requests
from django.conf import settings
from requests.adapters import HTTPAdapter

from google import genai
from google.genai import errors as genai_errors
from google.genai import types as genai_types

logger = logging.getLogger(__name__)


# Per-call metadata (provider, model, tokens, retries, fallback) from the
# most recent LLMClient.generate()/generate_stream() call in the current
# context - populated internally, read via get_last_llm_meta(). A
# ContextVar (not an instance attribute on the LLMClient singleton,
# which is shared process-wide) so concurrent requests/threads never
# see each other's metadata; same pattern as RAG.services.trace's
# trace_id/stage list. generate()/generate_stream()'s own signatures
# and return types are completely unchanged by this - a caller that
# doesn't call get_last_llm_meta() is unaffected.
_last_llm_meta_var: ContextVar[Optional[dict]] = ContextVar("last_llm_meta", default=None)


def get_last_llm_meta() -> Optional[dict]:
    """
    {"provider", "model", "providers_attempted", "retry_count",
    "fallback_enabled", "fallback_used", "latency_ms", "prompt_tokens",
    "completion_tokens", "total_tokens", "time_to_first_token_ms",
    "error_type", "error_message"} for the most recent generate()/
    generate_stream() call in this context, or None if none has run
    yet. Token fields are None when the provider didn't report usage
    (e.g. most streamed responses). "fallback_used" is True only when
    more than one provider was actually attempted - "fallback_enabled"
    reflects the setting regardless of whether a fallback was needed.
    """

    return _last_llm_meta_var.get()


# A shared, process-wide connection pool for every OpenAI-compatible REST
# provider (OpenRouter, Groq, ...) - without this, _OpenAICompatibleClient
# opened a fresh TCP+TLS connection on every single call. requests.Session
# is safe to share across threads for this usage (no per-request mutable
# state beyond the pool itself); each Django worker process gets its own.
_http_session = requests.Session()
_http_session.mount("https://", HTTPAdapter(pool_connections=10, pool_maxsize=10))
_http_session.mount("http://", HTTPAdapter(pool_connections=10, pool_maxsize=10))


# ============================================================
# Exceptions
# ============================================================

class LLMProviderError(Exception):
    """Base exception for any LLM provider failure - every provider client maps its native errors onto this hierarchy at the boundary, so callers never need to know which SDK/HTTP library a provider happens to use."""


class LLMAuthError(LLMProviderError):
    """Invalid/missing API key, or the key lacks access to the requested model. Never retried - a bad key won't start working on attempt 2."""


class LLMRateLimitError(LLMProviderError):
    """Rate limit or quota exceeded (HTTP 429, Gemini's ResourceExhausted, ...)."""


class LLMTimeoutError(LLMProviderError):
    """The request did not complete within settings.LLM_REQUEST_TIMEOUT."""


class AllProvidersFailedError(LLMProviderError):
    """Every provider in the fallback chain failed (or none are configured at all)."""


# ============================================================
# Base Class
# ============================================================

class BaseLLMClient:
    """Interface every provider client implements."""

    # Set by generate()/generate_stream() on success, to
    # {"prompt_tokens", "completion_tokens", "total_tokens"} when the
    # provider's response included usage data, else left None. A fresh
    # client instance is constructed per attempt in LLMClient.generate()
    # (see PROVIDER_REGISTRY["..."]["client_class"]()), so this is safe
    # to read as a plain instance attribute right after the call -no
    # shared/singleton state to worry about.
    last_usage = None

    def generate(self, prompt: str, temperature: float = None, response_format: str = None, max_tokens: int = None) -> str:
        raise NotImplementedError

    def generate_stream(self, prompt: str, temperature: float = None, response_format: str = None, max_tokens: int = None) -> Iterator[str]:
        raise NotImplementedError

    def health_check(self) -> dict:
        """A real minimal request (not just a key-presence check) - {"ok": bool, "latency_ms": int|None, "message": str}."""

        start = time.perf_counter()

        try:
            self.generate("Reply with exactly: OK", temperature=0.0)
        except LLMProviderError as exc:
            return {"ok": False, "latency_ms": None, "message": str(exc)}

        return {"ok": True, "latency_ms": round((time.perf_counter() - start) * 1000), "message": "Connected"}


# ============================================================
# Gemini Client
# ============================================================

class GeminiClient(BaseLLMClient):
    """
    Built on the current `google.genai` SDK (replaces the deprecated
    `google.generativeai`). `genai.Client` has no built-in retry by
    default (retry_options=None -> one attempt, reraise=True - see
    google.genai._api_client.retry_args), so a timeout/connect failure
    surfaces as a raw httpx exception here rather than a wrapped
    APIError; both are mapped below alongside APIError's HTTP-status
    based subclasses (ClientError/ServerError), the same status-code
    mapping style _map_http_error() already uses for OpenRouter/Groq.
    """

    PROVIDER_NAME = "Gemini"

    def __init__(self):

        self.client = genai.Client(
            api_key=settings.GEMINI_API_KEY,
            http_options=genai_types.HttpOptions(timeout=settings.LLM_REQUEST_TIMEOUT * 1000),
        )
        self.model = settings.LLM_MODEL

    def _generation_config(self, temperature, response_format, max_tokens=None):

        if temperature is None and response_format != "json" and max_tokens is None:
            return None

        return genai_types.GenerateContentConfig(
            temperature=temperature,
            response_mime_type="application/json" if response_format == "json" else None,
            max_output_tokens=max_tokens,
        )

    def _log_usage(self, response):

        usage = getattr(response, "usage_metadata", None)

        if usage:
            logger.info(
                "Gemini token usage: prompt=%s completion=%s total=%s",
                usage.prompt_token_count, usage.candidates_token_count, usage.total_token_count,
            )
            self.last_usage = {
                "prompt_tokens": usage.prompt_token_count,
                "completion_tokens": usage.candidates_token_count,
                "total_tokens": usage.total_token_count,
            }

    def _map_error(self, exc: Exception) -> LLMProviderError:

        if isinstance(exc, genai_errors.APIError):
            message = f"Gemini error ({exc.code}): {exc.message}"
            if exc.code in (401, 403):
                return LLMAuthError(message)
            if exc.code == 429:
                return LLMRateLimitError(message)
            if exc.code in (408, 504):
                return LLMTimeoutError(message)
            return LLMProviderError(message)

        if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError)):
            return LLMTimeoutError(f"Gemini request timed out: {exc}")

        return LLMProviderError(f"Gemini error: {exc}")

    def generate(self, prompt: str, temperature: float = None, response_format: str = None, max_tokens: int = None) -> str:

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._generation_config(temperature, response_format, max_tokens),
            )
        except (genai_errors.APIError, httpx.TimeoutException, httpx.ConnectError) as exc:
            raise self._map_error(exc) from exc

        self._log_usage(response)

        return response.text.strip()

    def generate_stream(self, prompt: str, temperature: float = None, response_format: str = None, max_tokens: int = None) -> Iterator[str]:

        try:
            response = self.client.models.generate_content_stream(
                model=self.model,
                contents=prompt,
                config=self._generation_config(temperature, response_format, max_tokens),
            )
            for chunk in response:
                if chunk.text:
                    yield chunk.text
        except (genai_errors.APIError, httpx.TimeoutException, httpx.ConnectError) as exc:
            raise self._map_error(exc) from exc


# ============================================================
# OpenAI-compatible REST clients (OpenRouter, Groq, ...)
# ============================================================

def _map_http_error(provider_name: str, exc: requests.exceptions.HTTPError) -> LLMProviderError:
    """Shared HTTP-status -> typed-exception mapping for every OpenAI-compatible REST provider."""

    status = exc.response.status_code if exc.response is not None else None
    message = f"{provider_name} error ({status}): {exc}"

    if status in (401, 403):
        return LLMAuthError(message)

    if status == 429:
        return LLMRateLimitError(message)

    return LLMProviderError(message)


class _OpenAICompatibleClient(BaseLLMClient):
    """
    Shared implementation for any OpenAI-compatible chat-completions
    REST API. Request building, SSE stream parsing, and HTTP error
    mapping all live here exactly once; a subclass only supplies
    PROVIDER_NAME/API_URL and how to read its own API key/model/extra
    headers from settings.
    """

    PROVIDER_NAME = "Provider"
    API_URL = None

    def _api_key(self) -> str:
        raise NotImplementedError

    def _model(self) -> str:
        raise NotImplementedError

    def _extra_headers(self) -> dict:
        return {}

    def _headers(self) -> dict:

        headers = {
            "Authorization": f"Bearer {self._api_key()}",
            "Content-Type": "application/json",
        }
        headers.update(self._extra_headers())

        return headers

    def _payload(self, prompt, temperature, response_format, stream=False, max_tokens=None) -> dict:

        payload = {
            "model": self._model(),
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature if temperature is not None else 0.2,
        }

        if response_format == "json":
            payload["response_format"] = {"type": "json_object"}

        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        if stream:
            payload["stream"] = True

        return payload

    def generate(self, prompt: str, temperature: float = None, response_format: str = None, max_tokens: int = None) -> str:

        try:
            response = _http_session.post(
                self.API_URL,
                headers=self._headers(),
                json=self._payload(prompt, temperature, response_format, max_tokens=max_tokens),
                timeout=settings.LLM_REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise LLMTimeoutError(f"{self.PROVIDER_NAME} request timed out") from exc
        except requests.exceptions.HTTPError as exc:
            raise _map_http_error(self.PROVIDER_NAME, exc) from exc
        except requests.exceptions.RequestException as exc:
            raise LLMProviderError(f"{self.PROVIDER_NAME} request failed: {exc}") from exc

        data = response.json()
        usage = data.get("usage")

        if usage:
            logger.info(
                "%s token usage: prompt=%s completion=%s total=%s",
                self.PROVIDER_NAME, usage.get("prompt_tokens"), usage.get("completion_tokens"), usage.get("total_tokens"),
            )
            self.last_usage = {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
            }

        try:
            return data["choices"][0]["message"]["content"].strip()
        except (KeyError, IndexError) as exc:
            raise LLMProviderError(f"{self.PROVIDER_NAME} returned an unexpected response shape") from exc

    def generate_stream(self, prompt: str, temperature: float = None, response_format: str = None, max_tokens: int = None) -> Iterator[str]:

        try:
            response = _http_session.post(
                self.API_URL,
                headers=self._headers(),
                json=self._payload(prompt, temperature, response_format, stream=True, max_tokens=max_tokens),
                timeout=settings.LLM_REQUEST_TIMEOUT,
                stream=True,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout as exc:
            raise LLMTimeoutError(f"{self.PROVIDER_NAME} request timed out") from exc
        except requests.exceptions.HTTPError as exc:
            raise _map_http_error(self.PROVIDER_NAME, exc) from exc
        except requests.exceptions.RequestException as exc:
            raise LLMProviderError(f"{self.PROVIDER_NAME} request failed: {exc}") from exc

        # Every OpenAI-compatible chat-completions API in this file
        # (OpenRouter, Groq) sends UTF-8 JSON, but the response's
        # Content-Type is "application/json" with no charset parameter,
        # so requests.Response.encoding comes back None. iter_lines(
        # decode_unicode=True) then falls back to chardet-style
        # guessing (apparent_encoding) per line, which frequently
        # misdetects short UTF-8 SSE chunks as Latin-1/Windows-1252 -
        # producing mojibake ("Ã£" etc.) in streamed answers. Forcing
        # utf-8 here removes the guess entirely. .json() in generate()
        # above doesn't need this - it has its own JSON-aware encoding
        # fallback (guess_json_utf) that's already UTF-8-correct.
        response.encoding = "utf-8"

        for line in response.iter_lines(decode_unicode=True):

            if not line or not line.startswith("data:"):
                continue

            chunk_data = line[len("data:"):].strip()

            if chunk_data == "[DONE]":
                break

            try:
                parsed = json.loads(chunk_data)
            except ValueError:
                continue

            delta = (parsed.get("choices") or [{}])[0].get("delta", {})
            content = delta.get("content")

            if content:
                yield content


class OpenRouterClient(_OpenAICompatibleClient):

    PROVIDER_NAME = "OpenRouter"
    API_URL = "https://openrouter.ai/api/v1/chat/completions"

    def _api_key(self):
        return settings.OPENROUTER_API_KEY

    def _model(self):
        return settings.OPENROUTER_MODEL

    def _extra_headers(self):
        return {
            "HTTP-Referer": getattr(settings, "SITE_URL", ""),
            "X-Title": getattr(settings, "SITE_NAME", "Cortex"),
        }


class GroqClient(_OpenAICompatibleClient):

    PROVIDER_NAME = "Groq"
    API_URL = "https://api.groq.com/openai/v1/chat/completions"

    def _api_key(self):
        return settings.GROQ_API_KEY

    def _model(self):
        return settings.GROQ_MODEL


# ============================================================
# Provider Registry - the extensibility point
# ============================================================

PROVIDER_REGISTRY = {
    "openrouter": {
        "label": "OpenRouter",
        "client_class": OpenRouterClient,
        "api_key_setting": "OPENROUTER_API_KEY",
        "model_setting": "OPENROUTER_MODEL",
        "free_models": [
            "openai/gpt-oss-20b:free",
            "google/gemma-4-26b-a4b-it:free",
            "nvidia/nemotron-nano-9b-v2:free",
        ],
    },
    "groq": {
        "label": "Groq",
        "client_class": GroqClient,
        "api_key_setting": "GROQ_API_KEY",
        "model_setting": "GROQ_MODEL",
        "free_models": [
            "llama-3.1-8b-instant",
            "llama-3.3-70b-versatile",
            "gemma2-9b-it",
        ],
    },
    "gemini": {
        "label": "Gemini",
        "client_class": GeminiClient,
        "api_key_setting": "GEMINI_API_KEY",
        "model_setting": "LLM_MODEL",
        "free_models": [
            "gemini-2.0-flash",
            "gemini-1.5-flash",
        ],
    },
}

# Order the *remaining* providers are tried in when
# settings.LLM_FALLBACK_ENABLED is True (off by default - see that
# setting) - Groq first (live-benchmarked as dramatically faster
# free-tier inference than OpenRouter's free model - see CLAUDE.md's
# performance audit), then OpenRouter, then Gemini. The configured
# primary provider (settings.LLM_PROVIDER) always goes first
# regardless of this order and regardless of the flag.
FALLBACK_PRIORITY = ["groq", "openrouter", "gemini"]


def _is_configured(provider: str) -> bool:
    return bool(getattr(settings, PROVIDER_REGISTRY[provider]["api_key_setting"], ""))


def _provider_model(provider: str) -> str:
    return getattr(settings, PROVIDER_REGISTRY[provider]["model_setting"], "")


# ============================================================
# Public Client
# ============================================================

class LLMClient:
    """
    Enterprise wrapper: builds a fallback chain from the currently
    configured primary provider + PROVIDER_REGISTRY/FALLBACK_PRIORITY,
    and walks it with per-provider retries and structured logging.
    Holds no provider/model state on self - see the module docstring
    for why that's the point.
    """

    def _build_chain(self) -> list:
        """
        Primary provider first, then - only when settings.LLM_FALLBACK_ENABLED
        is True - the rest of FALLBACK_PRIORITY that have an API key
        configured. With fallback disabled (the default), this returns
        at most one entry: the configured primary, or an empty list if
        it has no API key - never silently substitutes a different
        provider the admin didn't select.
        """

        primary = settings.LLM_PROVIDER.lower()
        chain = []

        if primary not in PROVIDER_REGISTRY:
            logger.warning("Unknown LLM_PROVIDER '%s' - ignoring it.", primary)
        elif _is_configured(primary):
            chain.append(primary)
        else:
            logger.warning("Primary provider '%s' has no API key configured.", primary)

        if not settings.LLM_FALLBACK_ENABLED:
            return chain

        for provider in FALLBACK_PRIORITY:
            if provider not in chain and _is_configured(provider):
                chain.append(provider)

        return chain

    def generate(self, prompt: str, temperature: float = None, response_format: str = None, max_tokens: int = None) -> str:

        chain = self._build_chain()

        if not chain:
            reason = (
                f"Configured provider '{settings.LLM_PROVIDER}' has no API key, and fallback is disabled "
                "(Admin > Settings > Enable Fallback)."
                if not settings.LLM_FALLBACK_ENABLED
                else "No LLM provider is configured - add an API key to .eee."
            )
            _last_llm_meta_var.set({
                "provider": "", "model": "", "providers_attempted": [], "retry_count": 0,
                "fallback_enabled": settings.LLM_FALLBACK_ENABLED, "fallback_used": False,
                "latency_ms": None, "prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
                "time_to_first_token_ms": None,
                "error_type": "AllProvidersFailedError", "error_message": reason,
            })
            raise AllProvidersFailedError(reason)

        last_exc = None
        providers_attempted = []
        total_attempts = 0

        for index, provider in enumerate(chain):

            client = PROVIDER_REGISTRY[provider]["client_class"]()
            model = _provider_model(provider)
            max_attempts = 1 + max(0, settings.LLM_MAX_RETRIES)
            providers_attempted.append(provider)

            for attempt in range(1, max_attempts + 1):

                total_attempts += 1
                start = time.perf_counter()

                try:
                    result = client.generate(prompt, temperature=temperature, response_format=response_format, max_tokens=max_tokens)
                except LLMAuthError as exc:
                    logger.warning(
                        "LLM call failed provider=%s model=%s attempt=%s reason=auth error=%s",
                        provider, model, attempt, exc,
                    )
                    last_exc = exc
                    break  # a bad key won't fix itself - skip straight to the next provider
                except LLMProviderError as exc:
                    latency_ms = round((time.perf_counter() - start) * 1000)
                    logger.warning(
                        "LLM call failed provider=%s model=%s attempt=%s/%s latency_ms=%s error=%s",
                        provider, model, attempt, max_attempts, latency_ms, exc,
                    )
                    last_exc = exc
                    continue  # retry this same provider if attempts remain
                else:
                    latency_ms = round((time.perf_counter() - start) * 1000)
                    logger.info(
                        "LLM call succeeded provider=%s model=%s attempt=%s latency_ms=%s",
                        provider, model, attempt, latency_ms,
                    )
                    usage = client.last_usage or {}
                    _last_llm_meta_var.set({
                        "provider": provider, "model": model,
                        "providers_attempted": providers_attempted, "retry_count": total_attempts - 1,
                        "fallback_enabled": settings.LLM_FALLBACK_ENABLED, "fallback_used": len(providers_attempted) > 1,
                        "latency_ms": latency_ms,
                        "prompt_tokens": usage.get("prompt_tokens"),
                        "completion_tokens": usage.get("completion_tokens"),
                        "total_tokens": usage.get("total_tokens"),
                        "time_to_first_token_ms": None,
                        "error_type": "", "error_message": "",
                    })
                    return result

            if index < len(chain) - 1:
                logger.info("Falling back from %s to %s.", provider, chain[index + 1])

        logger.error("All configured LLM providers failed. Last error: %s", last_exc)
        _last_llm_meta_var.set({
            "provider": providers_attempted[-1] if providers_attempted else "",
            "model": _provider_model(providers_attempted[-1]) if providers_attempted else "",
            "providers_attempted": providers_attempted, "retry_count": total_attempts,
            "fallback_enabled": settings.LLM_FALLBACK_ENABLED, "fallback_used": len(providers_attempted) > 1,
            "latency_ms": None, "prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
            "time_to_first_token_ms": None,
            "error_type": type(last_exc).__name__ if last_exc else "AllProvidersFailedError",
            "error_message": str(last_exc) if last_exc else "All configured LLM providers failed.",
        })
        raise AllProvidersFailedError(f"All configured LLM providers failed: {last_exc}") from last_exc

    def generate_stream(self, prompt: str, temperature: float = None, response_format: str = None, max_tokens: int = None) -> Iterator[str]:
        """
        Same fallback chain as generate(), but fallback is only
        possible BEFORE the first chunk is yielded from a given
        provider - once partial text has already reached the caller,
        silently restarting from another provider would duplicate or
        corrupt what they've seen, so a mid-stream failure propagates
        instead of falling back.
        """

        chain = self._build_chain()

        if not chain:
            reason = (
                f"Configured provider '{settings.LLM_PROVIDER}' has no API key, and fallback is disabled "
                "(Admin > Settings > Enable Fallback)."
                if not settings.LLM_FALLBACK_ENABLED
                else "No LLM provider is configured - add an API key to .eee."
            )
            raise AllProvidersFailedError(reason)

        last_exc = None
        providers_attempted = []

        for index, provider in enumerate(chain):

            client = PROVIDER_REGISTRY[provider]["client_class"]()
            model = _provider_model(provider)
            started = False
            first_token_ms = None
            start = time.perf_counter()
            providers_attempted.append(provider)

            try:
                for chunk in client.generate_stream(prompt, temperature=temperature, response_format=response_format, max_tokens=max_tokens):
                    if not started:
                        started = True
                        first_token_ms = round((time.perf_counter() - start) * 1000)
                        logger.info(
                            "LLM stream started provider=%s model=%s latency_ms=%s",
                            provider, model, first_token_ms,
                        )
                    yield chunk
            except LLMProviderError as exc:
                if started:
                    logger.error("LLM stream failed mid-stream provider=%s model=%s error=%s", provider, model, exc)
                    raise
                logger.warning("LLM stream failed before first chunk provider=%s model=%s error=%s", provider, model, exc)
                last_exc = exc
                if index < len(chain) - 1:
                    logger.info("Falling back from %s to %s.", provider, chain[index + 1])
                continue

            total_latency_ms = round((time.perf_counter() - start) * 1000)
            logger.info("LLM stream completed provider=%s model=%s", provider, model)
            _last_llm_meta_var.set({
                "provider": provider, "model": model,
                "providers_attempted": providers_attempted, "retry_count": len(providers_attempted) - 1,
                "fallback_enabled": settings.LLM_FALLBACK_ENABLED, "fallback_used": len(providers_attempted) > 1,
                "latency_ms": total_latency_ms,
                # Streamed responses don't carry a usage block (no
                # provider here sends one over SSE) - tokens stay
                # unknown rather than guessed.
                "prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
                "time_to_first_token_ms": first_token_ms,
                "error_type": "", "error_message": "",
            })
            return

        logger.error("All configured LLM providers failed to stream. Last error: %s", last_exc)
        _last_llm_meta_var.set({
            "provider": providers_attempted[-1] if providers_attempted else "",
            "model": _provider_model(providers_attempted[-1]) if providers_attempted else "",
            "providers_attempted": providers_attempted, "retry_count": len(providers_attempted),
            "fallback_enabled": settings.LLM_FALLBACK_ENABLED, "fallback_used": len(providers_attempted) > 1,
            "latency_ms": None, "prompt_tokens": None, "completion_tokens": None, "total_tokens": None,
            "time_to_first_token_ms": None,
            "error_type": type(last_exc).__name__ if last_exc else "AllProvidersFailedError",
            "error_message": str(last_exc) if last_exc else "All configured LLM providers failed.",
        })
        raise AllProvidersFailedError(f"All configured LLM providers failed: {last_exc}") from last_exc

    def health_check(self, provider: str) -> dict:
        """Tests exactly the named provider (bypassing the fallback chain) - for the Settings page's "Test Connection" button."""

        if provider not in PROVIDER_REGISTRY:
            return {"ok": False, "latency_ms": None, "message": f"Unknown provider '{provider}'."}

        if not _is_configured(provider):
            return {"ok": False, "latency_ms": None, "message": "No API key configured."}

        client = PROVIDER_REGISTRY[provider]["client_class"]()

        return client.health_check()


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
    Kept for backward compatibility - system_config_service.save_config()
    calls this whenever an admin saves Settings. No longer strictly
    load-bearing: LLMClient reads settings.LLM_PROVIDER and every
    provider's model setting fresh on every generate()/
    generate_stream() call rather than caching them at construction
    (see the module docstring), so the existing singleton already
    reflects a config change on its very next call regardless. This
    still swaps in a new (equally stateless) instance, which is
    harmless.
    """

    global _client
    _client = None


# ============================================================
# Shared JSON-mode helpers
# ============================================================

def parse_json_response(raw: str) -> Optional[dict]:
    """
    Parses/validates a response_format="json" LLM response into a
    dict - None (never raises) on an empty response, invalid JSON, or a
    valid-but-non-object payload (e.g. a bare JSON list/string). Shared
    by generate_json() below and RAG.services.llm_service.generate_answer():
    both need this exact parse/validate step, but each needs a different
    try/except boundary around the *LLM call itself* (generate_answer()
    must distinguish AllProvidersFailedError - a service-unavailable
    situation - from a parsing failure, which generate_json()'s callers
    don't care to distinguish), so only the parsing is factored out, not
    the call.
    """

    if not raw:
        return None

    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        return None

    return parsed if isinstance(parsed, dict) else None


def generate_json(prompt: str, temperature: float = 0.2, context_label: str = "") -> Optional[dict]:
    """
    Never-raise JSON-mode call - extracted from AI Tasks' original
    _call_llm_json() (RAG.services.ai_tasks_engine_service), which was
    the first place this codebase proved the response_format="json" +
    parse/validate pattern out. The one place any caller that doesn't
    need to distinguish *why* it failed goes through, so a second copy
    of this call+parse+log logic never needs to exist.

    Returns a parsed dict on success, or None on any failure (network
    error, provider outage, empty response, malformed JSON, non-dict
    payload) - logged in every failure case, never raised. `context_label`,
    if given, is appended to the log message only (e.g. "AI Task run 5:
    document Foo.pdf") - purely for readability, no behavior depends on it.
    """

    suffix = f" for {context_label}" if context_label else ""

    try:
        raw = get_llm().generate(prompt, temperature=temperature, response_format="json")
    except Exception:
        logger.exception("generate_json: LLM call failed%s", suffix)
        return None

    parsed = parse_json_response(raw)

    if parsed is None:
        logger.warning("generate_json: empty/invalid/non-object JSON from LLM%s", suffix)

    return parsed
