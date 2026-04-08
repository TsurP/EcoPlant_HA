"""Deterministic (no-LLM) tests for the fail-closed guards in AnswerNLQueryUseCase.

These tests exercise the logic that was previously uncovered because
test_llm_use_cases.py is entirely behind the ``openai_live`` marker.

Scenarios covered:
- LLM returns a query with metric_name=None  → clarification (finding 1)
- LLM returns a query with malformed start_time → clarification (finding 2)
- LLM returns a query with malformed end_time  → clarification (finding 2)
- LLM returns a valid query                   → repo is called with correct filters
- LLM signals needs_clarification directly    → repo is never called
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypeVar

import pytest
from pydantic import BaseModel

from air_platform.llm.schemas import MetricAggregation, StructuredMetricQuery, SupportedMetric
from air_platform.llm.use_cases import AnswerNLQueryUseCase
from air_platform.metrics.models import MetricQuery, MetricResult

_T = TypeVar("_T", bound=BaseModel)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


class _StubLLM:
    """Returns a pre-configured StructuredMetricQuery from generate_structured."""

    def __init__(self, query: StructuredMetricQuery) -> None:
        self._query = query

    def generate_text(self, system_prompt: str, user_content: str) -> str:  # noqa: ARG002
        return "stub answer"

    def generate_structured(
        self,
        system_prompt: str,  # noqa: ARG002
        user_content: str,  # noqa: ARG002
        schema: type[_T],  # noqa: ARG002
    ) -> _T:
        return self._query  # type: ignore[return-value]


class _StubRepo:
    """Records calls and returns a configurable metric list."""

    def __init__(self, metrics: list[MetricResult] | None = None) -> None:
        self._metrics = metrics or []
        self.queries: list[MetricQuery] = []

    def save_metric_results(self, results: list[MetricResult]) -> None:  # pragma: no cover
        raise NotImplementedError

    def get_metric_results(self, query: MetricQuery) -> list[MetricResult]:
        self.queries.append(query)
        return list(self._metrics)


def _use_case(query: StructuredMetricQuery, metrics: list[MetricResult] | None = None) -> tuple[
    AnswerNLQueryUseCase,
    _StubRepo,
]:
    repo = _StubRepo(metrics)
    uc = AnswerNLQueryUseCase(metric_repository=repo, llm=_StubLLM(query))
    return uc, repo


def _make_metric(metric_name: str = "average_pressure_bar", value: float = 8.0) -> MetricResult:
    now = datetime(2024, 2, 1, 6, 0, 0, tzinfo=UTC)
    return MetricResult(
        station_id="s1",
        device_id="d1",
        metric_name=metric_name,
        metric_value=value,
        unit="bar",
        window_start=datetime(2024, 2, 1, 0, 0, tzinfo=UTC),
        window_end=now,
        computed_at=now,
        resample_frequency="15min",
        missing_strategy="fill",
    )


# ---------------------------------------------------------------------------
# Finding 1: metric_name=None must be rejected before hitting the repository
# ---------------------------------------------------------------------------


class TestMissingMetricNameGuard:
    def test_none_metric_name_returns_clarification(self) -> None:
        """LLM omits metric_name → clarification result, repo never queried."""
        uc, repo = _use_case(StructuredMetricQuery(station_id="s1", metric_name=None))

        result = uc.execute("any question")

        assert result.parsed_query.needs_clarification is True
        assert result.aggregate_value is None
        assert result.metric_results == []
        assert repo.queries == [], "repo must not be called when metric_name is absent"

    def test_none_metric_name_with_station_id_still_rejected(self) -> None:
        """With a valid station_id but no metric_name: still rejected (prevents cross-type mix)."""
        uc, repo = _use_case(
            StructuredMetricQuery(station_id="station-1", metric_name=None)
        )

        result = uc.execute("show me all metrics for station-1")

        assert result.parsed_query.needs_clarification is True
        assert repo.queries == []

    def test_valid_metric_name_and_station_proceeds_to_repo(self) -> None:
        """Sanity-check: a well-formed parse reaches the repository."""
        metrics = [_make_metric(value=8.0), _make_metric(value=9.0)]
        uc, repo = _use_case(
            StructuredMetricQuery(
                station_id="s1",
                metric_name=SupportedMetric.AVERAGE_PRESSURE_BAR,
                aggregation=MetricAggregation.MEAN,
            ),
            metrics=metrics,
        )

        result = uc.execute("mean pressure for s1")

        assert result.parsed_query.needs_clarification is False
        assert len(repo.queries) == 1
        assert result.aggregate_value == pytest.approx(8.5)


# ---------------------------------------------------------------------------
# Finding 2: malformed time strings must fail closed (not silently drop filter)
# ---------------------------------------------------------------------------


class TestMalformedTimeFilterGuard:
    @pytest.mark.parametrize(
        "start_time,end_time",
        [
            ("not-a-date", None),
            (None, "yesterday"),
            ("2024-13-01T00:00:00", None),  # month 13
            (None, "2024-01-32T00:00:00"),  # day 32
        ],
    )
    def test_invalid_time_string_returns_clarification(
        self, start_time: str | None, end_time: str | None
    ) -> None:
        """Any non-ISO time string from the LLM must produce clarification, not a broad query."""
        uc, repo = _use_case(
            StructuredMetricQuery(
                station_id="s1",
                metric_name=SupportedMetric.AVERAGE_PRESSURE_BAR,
                start_time=start_time,
                end_time=end_time,
            )
        )

        result = uc.execute("any question")

        assert result.parsed_query.needs_clarification is True, (
            f"Expected clarification for start={start_time!r} end={end_time!r}"
        )
        assert result.aggregate_value is None
        assert result.metric_results == []
        assert repo.queries == [], "repo must not be called when time filter is unparseable"

    def test_valid_iso_times_pass_through_to_repo(self) -> None:
        """Valid ISO-8601 strings are parsed and forwarded to the repository."""
        start = "2024-02-01T00:00:00"
        end = "2024-02-01T06:00:00"
        uc, repo = _use_case(
            StructuredMetricQuery(
                station_id="s1",
                metric_name=SupportedMetric.AVERAGE_PRESSURE_BAR,
                start_time=start,
                end_time=end,
            )
        )

        uc.execute("any question")

        assert len(repo.queries) == 1
        q = repo.queries[0]
        assert q.start_time == datetime(2024, 2, 1, 0, 0, 0)
        assert q.end_time == datetime(2024, 2, 1, 6, 0, 0)

    def test_none_times_pass_through_as_none(self) -> None:
        """None time filters are forwarded as None (no time filter applied)."""
        uc, repo = _use_case(
            StructuredMetricQuery(
                station_id="s1",
                metric_name=SupportedMetric.AVERAGE_PRESSURE_BAR,
                start_time=None,
                end_time=None,
            )
        )

        uc.execute("any question")

        assert len(repo.queries) == 1
        assert repo.queries[0].start_time is None
        assert repo.queries[0].end_time is None
