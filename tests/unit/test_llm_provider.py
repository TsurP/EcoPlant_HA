"""Live OpenAI-backed tests for the provider surface."""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import BaseModel

from air_platform.llm.openai_provider import OpenAIProvider

pytestmark = pytest.mark.openai_live


class _ExactStructuredResponse(BaseModel):
    status: Literal["ok"]
    value: Literal[42]


def test_generate_text_returns_non_empty_content(live_openai_provider: OpenAIProvider) -> None:
    result = live_openai_provider.generate_text(
        system_prompt="Reply briefly and include the token TEST_OK in your answer.",
        user_content="Acknowledge this request.",
    )

    assert isinstance(result, str)
    assert result.strip()
    assert "TEST_OK" in result


def test_generate_structured_returns_valid_model(
    live_openai_provider: OpenAIProvider,
) -> None:
    result = live_openai_provider.generate_structured(
        system_prompt=(
            "Return the requested structured response exactly. Set status to ok and value to 42."
        ),
        user_content="Populate the schema now.",
        schema=_ExactStructuredResponse,
    )

    assert result == _ExactStructuredResponse(status="ok", value=42)
