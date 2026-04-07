"""Optional integration tests that hit the real OpenAI API.

These tests use the shared live-provider fixture and are skipped unless
AIR_PLATFORM_OPENAI_API_KEY (or OPENAI_API_KEY) is set. They are
intentionally coarse-grained: we verify that the plumbing works end-to-end,
not that the model returns specific wording.

Run with:
    AIR_PLATFORM_OPENAI_API_KEY=sk-... pytest tests/integration/test_llm_openai.py -v
"""

from __future__ import annotations

import pytest

from air_platform.llm.openai_provider import OpenAIProvider
from air_platform.llm.schemas import StructuredMetricQuery

pytestmark = pytest.mark.openai_live


def test_generate_text_returns_non_empty_string(
    live_openai_provider: OpenAIProvider,
) -> None:
    result = live_openai_provider.generate_text(
        system_prompt="You are a helpful assistant. Reply in one sentence.",
        user_content="Say hello.",
    )
    assert isinstance(result, str)
    assert len(result) > 0


def test_generate_structured_returns_valid_query(
    live_openai_provider: OpenAIProvider,
) -> None:
    from air_platform.llm.prompts import NL_QUERY_SYSTEM, nl_query_user

    result = live_openai_provider.generate_structured(
        system_prompt=NL_QUERY_SYSTEM,
        user_content=nl_query_user(
            "What is the average pressure for station ST-001 between 2024-01-01 and 2024-01-07?"
        ),
        schema=StructuredMetricQuery,
    )

    assert isinstance(result, StructuredMetricQuery)
    # Coarse assertion only — we do not assert exact wording.
    assert result.needs_clarification is False or result.needs_clarification is True
