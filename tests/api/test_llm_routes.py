"""API-level tests for LLM endpoints.

The LLM dependency is overridden with a mock in every test — no real
OpenAI calls are made.  We test HTTP status codes, response structure,
and graceful-degradation behaviour.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from air_platform.config import AppSettings
from air_platform.errors import DataNotFoundError, LLMNotConfiguredError
from air_platform.llm.schemas import MetricAggregation, StructuredMetricQuery, SupportedMetric
from air_platform.llm.use_cases import (
    AnswerNLQueryUseCase,
    DQReportResult,
    GenerateDataQualityReportUseCase,
    NLQueryResult,
    StationSummaryResult,
    SummarizeStationHealthUseCase,
)
from air_platform.metrics.models import MetricResult
from air_platform.service.app import create_app
from air_platform.service.dependencies import (
    get_dq_report_use_case,
    get_nl_query_use_case,
    get_station_summary_use_case,
)
from tests.constants import TEST_STATION_ID

_NOW = datetime(2024, 2, 1, 6, 0, 0, tzinfo=UTC)


def _make_metric(
    station_id: str = TEST_STATION_ID,
    metric_name: str = "average_pressure_bar",
    metric_value: float = 8.5,
) -> MetricResult:
    return MetricResult(
        station_id=station_id,
        device_id="device-1",
        metric_name=metric_name,
        metric_value=metric_value,
        unit="bar",
        window_start=datetime(2024, 2, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2024, 2, 1, 6, 0, tzinfo=UTC),
        computed_at=_NOW,
        resample_frequency="15min",
        missing_strategy="fill",
    )


def _summary_result(
    station_id: str = TEST_STATION_ID,
    summary: str | None = "All good.",
    llm_failed: bool = False,
    warning: str | None = None,
) -> StationSummaryResult:
    return StationSummaryResult(
        station_id=station_id,
        start_time=None,
        end_time=None,
        summary=summary,
        metrics=[_make_metric(station_id=station_id)],
        llm_failed=llm_failed,
        warning=warning,
    )


def _nl_result(
    needs_clarification: bool = False,
    clarification_message: str | None = None,
    aggregate_value: float | None = 8.5,
    llm_rendering_failed: bool = False,
    warning: str | None = None,
) -> NLQueryResult:
    pq = StructuredMetricQuery(
        station_id=TEST_STATION_ID,
        metric_name=SupportedMetric.AVERAGE_PRESSURE_BAR,
        aggregation=MetricAggregation.MEAN,
        needs_clarification=needs_clarification,
        clarification_message=clarification_message,
    )
    return NLQueryResult(
        original_question="What is the pressure?",
        parsed_query=pq,
        metric_results=[_make_metric()] if aggregate_value is not None else [],
        aggregate_value=aggregate_value,
        natural_language_answer="It was 8.5 bar." if not llm_rendering_failed else None,
        llm_rendering_failed=llm_rendering_failed,
        warning=clarification_message if needs_clarification else warning,
    )


def _dq_result(
    station_id: str = TEST_STATION_ID,
    report: str | None = "Quality is fine.",
    llm_failed: bool = False,
    llm_warning: str | None = None,
) -> DQReportResult:
    return DQReportResult(
        station_id=station_id,
        start_time=None,
        end_time=None,
        report=report,
        total_rows_read=100,
        total_rows_after_cleaning=98,
        column_missing_pct={"discharge_pressure": 2.0},
        out_of_range_counts={},
        malformed_value_counts={},
        gap_count=0,
        flatline_count=0,
        warnings=[],
        llm_failed=llm_failed,
        llm_warning=llm_warning,
    )


def _make_client(
    app_settings: AppSettings,
    summary_use_case: SummarizeStationHealthUseCase | None = None,
    nl_use_case: AnswerNLQueryUseCase | None = None,
    dq_use_case: GenerateDataQualityReportUseCase | None = None,
) -> TestClient:
    app = create_app(app_settings)
    if summary_use_case is not None:
        app.dependency_overrides[get_station_summary_use_case] = lambda: summary_use_case
    if nl_use_case is not None:
        app.dependency_overrides[get_nl_query_use_case] = lambda: nl_use_case
    if dq_use_case is not None:
        app.dependency_overrides[get_dq_report_use_case] = lambda: dq_use_case
    return TestClient(app)


# ---------------------------------------------------------------------------
# Station health summary endpoint
# ---------------------------------------------------------------------------


class TestStationHealthSummaryEndpoint:
    def test_happy_path_returns_200(self, app_settings: AppSettings) -> None:
        uc = MagicMock(spec=SummarizeStationHealthUseCase)
        uc.execute.return_value = _summary_result()
        client = _make_client(app_settings, summary_use_case=uc)

        response = client.post(f"/stations/{TEST_STATION_ID}/summary")

        assert response.status_code == 200
        payload = response.json()
        assert payload["station_id"] == TEST_STATION_ID
        assert payload["summary"] == "All good."
        assert isinstance(payload["metrics"], list)
        assert payload["llm_failed"] is False

    def test_includes_time_window_from_request(self, app_settings: AppSettings) -> None:
        uc = MagicMock(spec=SummarizeStationHealthUseCase)
        uc.execute.return_value = _summary_result()
        client = _make_client(app_settings, summary_use_case=uc)

        response = client.post(
            f"/stations/{TEST_STATION_ID}/summary",
            json={
                "start_time": "2024-02-01T00:00:00+00:00",
                "end_time": "2024-02-01T06:00:00+00:00",
            },
        )

        assert response.status_code == 200
        _, kwargs = uc.execute.call_args
        assert kwargs["start_time"] is not None

    def test_returns_degraded_response_when_llm_fails(self, app_settings: AppSettings) -> None:
        uc = MagicMock(spec=SummarizeStationHealthUseCase)
        uc.execute.return_value = _summary_result(
            summary=None, llm_failed=True, warning="LLM down."
        )
        client = _make_client(app_settings, summary_use_case=uc)

        response = client.post(f"/stations/{TEST_STATION_ID}/summary")

        assert response.status_code == 200
        payload = response.json()
        assert payload["llm_failed"] is True
        assert payload["summary"] is None
        assert payload["warning"] == "LLM down."
        assert len(payload["metrics"]) > 0

    def test_returns_404_when_no_metrics(self, app_settings: AppSettings) -> None:
        uc = MagicMock(spec=SummarizeStationHealthUseCase)
        uc.execute.side_effect = DataNotFoundError("No metrics for station.")
        client = _make_client(app_settings, summary_use_case=uc)

        response = client.post("/stations/unknown/summary")

        assert response.status_code == 404

    def test_returns_503_when_llm_not_configured(self, app_settings: AppSettings) -> None:
        app = create_app(app_settings)

        def raise_not_configured():
            raise LLMNotConfiguredError("No API key.")

        app.dependency_overrides[get_station_summary_use_case] = raise_not_configured
        client = TestClient(app, raise_server_exceptions=False)

        response = client.post(f"/stations/{TEST_STATION_ID}/summary")

        assert response.status_code == 503


# ---------------------------------------------------------------------------
# Natural-language query endpoint
# ---------------------------------------------------------------------------


class TestNLQueryEndpoint:
    def test_happy_path_returns_200(self, app_settings: AppSettings) -> None:
        uc = MagicMock(spec=AnswerNLQueryUseCase)
        uc.execute.return_value = _nl_result()
        client = _make_client(app_settings, nl_use_case=uc)

        response = client.post("/llm/query", json={"question": "What is the pressure?"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["original_question"] == "What is the pressure?"
        assert payload["aggregate_value"] == pytest.approx(8.5)
        assert payload["parsed_query"]["metric_name"] == "average_pressure_bar"

    def test_returns_clarification_response(self, app_settings: AppSettings) -> None:
        uc = MagicMock(spec=AnswerNLQueryUseCase)
        uc.execute.return_value = _nl_result(
            needs_clarification=True,
            clarification_message="Please specify a station.",
            aggregate_value=None,
        )
        client = _make_client(app_settings, nl_use_case=uc)

        response = client.post("/llm/query", json={"question": "What is the pressure?"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["parsed_query"]["needs_clarification"] is True
        assert payload["aggregate_value"] is None
        assert "station" in payload["warning"].lower()

    def test_degraded_rendering_still_returns_200(self, app_settings: AppSettings) -> None:
        uc = MagicMock(spec=AnswerNLQueryUseCase)
        uc.execute.return_value = _nl_result(
            llm_rendering_failed=True,
            warning="LLM rendering failed.",
        )
        client = _make_client(app_settings, nl_use_case=uc)

        response = client.post("/llm/query", json={"question": "pressure?"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["llm_rendering_failed"] is True
        assert payload["aggregate_value"] is not None

    def test_missing_question_returns_422(self, app_settings: AppSettings) -> None:
        uc = MagicMock(spec=AnswerNLQueryUseCase)
        client = _make_client(app_settings, nl_use_case=uc)

        response = client.post("/llm/query", json={})

        assert response.status_code == 422

    def test_parse_failure_returns_clarification_response(self, app_settings: AppSettings) -> None:
        """When generate_structured raises LLMError, the use case falls back gracefully."""

        uc = MagicMock(spec=AnswerNLQueryUseCase)
        uc.execute.return_value = _nl_result(
            needs_clarification=True,
            clarification_message="The query parser is temporarily unavailable.",
            aggregate_value=None,
            llm_rendering_failed=True,
        )
        client = _make_client(app_settings, nl_use_case=uc)

        response = client.post("/llm/query", json={"question": "pressure?"})

        assert response.status_code == 200
        payload = response.json()
        assert payload["parsed_query"]["needs_clarification"] is True
        assert payload["aggregate_value"] is None


# ---------------------------------------------------------------------------
# Data quality report endpoint
# ---------------------------------------------------------------------------


class TestDQReportEndpoint:
    def test_happy_path_returns_200(self, app_settings: AppSettings) -> None:
        uc = MagicMock(spec=GenerateDataQualityReportUseCase)
        uc.execute.return_value = _dq_result()
        client = _make_client(app_settings, dq_use_case=uc)

        response = client.post(f"/stations/{TEST_STATION_ID}/quality-report")

        assert response.status_code == 200
        payload = response.json()
        assert payload["station_id"] == TEST_STATION_ID
        assert payload["report"] == "Quality is fine."
        assert payload["total_rows_read"] == 100
        assert payload["llm_failed"] is False

    def test_structured_findings_present_when_llm_fails(self, app_settings: AppSettings) -> None:
        uc = MagicMock(spec=GenerateDataQualityReportUseCase)
        uc.execute.return_value = _dq_result(report=None, llm_failed=True, llm_warning="LLM down.")
        client = _make_client(app_settings, dq_use_case=uc)

        response = client.post(f"/stations/{TEST_STATION_ID}/quality-report")

        assert response.status_code == 200
        payload = response.json()
        assert payload["llm_failed"] is True
        assert payload["report"] is None
        assert payload["total_rows_read"] == 100
        assert payload["llm_warning"] == "LLM down."

    def test_accepts_time_range_body(self, app_settings: AppSettings) -> None:
        uc = MagicMock(spec=GenerateDataQualityReportUseCase)
        uc.execute.return_value = _dq_result()
        client = _make_client(app_settings, dq_use_case=uc)

        response = client.post(
            f"/stations/{TEST_STATION_ID}/quality-report",
            json={"start_time": "2024-02-01T00:00:00+00:00"},
        )

        assert response.status_code == 200
        _, kwargs = uc.execute.call_args
        assert kwargs["start_time"] is not None
