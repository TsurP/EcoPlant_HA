"""LLM provider abstraction.

Application code must depend on this protocol, never on a concrete SDK.
"""

from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

_T = TypeVar("_T", bound=BaseModel)


class LLMProvider(Protocol):
    """Interface for LLM operations used by the application layer.

    Implementations must support:
    - Free-text generation (summarisation, phrasing)
    - Structured-output generation validated against a Pydantic schema
    """

    def generate_text(self, system_prompt: str, user_content: str) -> str:
        """Generate free-form text.

        Args:
            system_prompt: Instruction context for the model.
            user_content:  The user-facing input / data payload.

        Returns:
            The model's text response.

        Raises:
            LLMTimeoutError: Call exceeded the configured timeout.
            LLMProviderError: Provider returned an unrecoverable error.
        """
        ...

    def generate_structured(
        self,
        system_prompt: str,
        user_content: str,
        schema: type[_T],
    ) -> _T:
        """Generate structured output validated against *schema*.

        The model is instructed to produce JSON that matches *schema*.
        The response is parsed and returned as a model instance.

        Args:
            system_prompt: Instruction context including schema guidance.
            user_content:  The user-facing input / data payload.
            schema:        Pydantic model class to parse the response into.

        Returns:
            A validated instance of *schema*.

        Raises:
            LLMStructuredOutputError: Response could not be parsed / validated.
            LLMTimeoutError: Call exceeded the configured timeout.
            LLMProviderError: Provider returned an unrecoverable error.
        """
        ...
