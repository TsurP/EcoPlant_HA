"""OpenAI-backed LLM provider implementation."""

from __future__ import annotations

import logging
import random
import time
from collections.abc import Callable
from typing import TypeVar

import openai
from pydantic import BaseModel

from air_platform.errors import (
    LLMProviderError,
    LLMStructuredOutputError,
    LLMTimeoutError,
)

logger = logging.getLogger(__name__)

_T = TypeVar("_T", bound=BaseModel)
_RT = TypeVar("_RT")  # Unconstrained, used by the retry helper.

# HTTP status codes that indicate a transient server-side failure.
_TRANSIENT_STATUS_CODES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_MAX_BACKOFF_SECONDS: float = 30.0


class OpenAIProvider:
    """LLM provider backed by the OpenAI Chat Completions API.

    Implements the :class:`air_platform.llm.provider.LLMProvider` protocol.

    Retry behaviour:
    - Retries on transient failures: timeout, rate-limit (429), 5xx.
    - Does **not** retry on validation / parse errors or non-transient 4xx.
    - Uses exponential backoff with jitter between attempts.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o-mini",
        timeout_seconds: float = 30.0,
        max_retries: int = 3,
    ) -> None:
        self._client = openai.OpenAI(api_key=api_key, timeout=timeout_seconds)
        self._model = model
        self._max_retries = max_retries

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def generate_text(self, system_prompt: str, user_content: str) -> str:
        """Generate free-form text."""
        logger.info("llm.generate_text model=%s", self._model)

        def call() -> str:
            return self._do_generate_text(system_prompt, user_content)

        return self._with_retry(call, "generate_text")

    def generate_structured(
        self,
        system_prompt: str,
        user_content: str,
        schema: type[_T],
    ) -> _T:
        """Generate structured output validated against *schema*."""
        logger.info("llm.generate_structured model=%s schema=%s", self._model, schema.__name__)

        def call() -> _T:
            return self._do_generate_structured(system_prompt, user_content, schema)

        return self._with_retry(call, "generate_structured")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _do_generate_text(self, system_prompt: str, user_content: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        content = response.choices[0].message.content
        if content is None:
            raise LLMProviderError("Model returned empty content for generate_text")
        return content

    def _do_generate_structured(
        self,
        system_prompt: str,
        user_content: str,
        schema: type[_T],
    ) -> _T:
        try:
            response = self._client.beta.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                response_format=schema,
            )
        except openai.LengthFinishReasonError as exc:
            raise LLMStructuredOutputError(
                f"Response truncated before completing {schema.__name__} schema"
            ) from exc

        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise LLMStructuredOutputError(
                f"Model returned null structured content for schema {schema.__name__}"
            )
        return parsed

    def _with_retry(self, fn: Callable[[], _RT], caller: str) -> _RT:
        """Execute *fn* with exponential-backoff retry on transient errors."""
        start = time.monotonic()
        last_exc: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                result = fn()
                logger.info("llm.%s completed latency=%.2fs", caller, time.monotonic() - start)
                return result

            except openai.APITimeoutError as exc:
                logger.warning("llm.%s timeout attempt=%d/%d", caller, attempt, self._max_retries)
                last_exc = exc
                if attempt < self._max_retries:
                    self._backoff(attempt)

            except openai.RateLimitError as exc:
                logger.warning(
                    "llm.%s rate_limited attempt=%d/%d", caller, attempt, self._max_retries
                )
                last_exc = exc
                if attempt < self._max_retries:
                    self._backoff(attempt)

            except openai.APIStatusError as exc:
                if exc.status_code in _TRANSIENT_STATUS_CODES:
                    logger.warning(
                        "llm.%s http_status=%d attempt=%d/%d",
                        caller,
                        exc.status_code,
                        attempt,
                        self._max_retries,
                    )
                    last_exc = exc
                    if attempt < self._max_retries:
                        self._backoff(attempt)
                else:
                    raise LLMProviderError(
                        f"llm.{caller} non-transient provider error: HTTP {exc.status_code}"
                    ) from exc

            except LLMStructuredOutputError:
                # Validation / parse failures are not retried.
                raise

            except Exception as exc:
                # Any other SDK or network exception (e.g. APIConnectionError) is
                # immediately re-raised as LLMProviderError so callers see a typed
                # LLMError rather than a raw SDK exception or a 500.
                raise LLMProviderError(
                    f"llm.{caller} unexpected error: {type(exc).__name__}: {exc}"
                ) from exc

        # All retries exhausted — map the last exception.
        if isinstance(last_exc, openai.APITimeoutError):
            raise LLMTimeoutError(
                f"llm.{caller} timed out after {self._max_retries} attempts"
            ) from last_exc
        raise LLMProviderError(
            f"llm.{caller} failed after {self._max_retries} attempts"
        ) from last_exc

    def _backoff(self, attempt: int) -> None:
        jitter = random.uniform(0.0, 0.5)
        delay = min(2.0 ** (attempt - 1) + jitter, _MAX_BACKOFF_SECONDS)
        logger.debug("llm.backoff delay=%.2fs attempt=%d", delay, attempt)
        time.sleep(delay)
