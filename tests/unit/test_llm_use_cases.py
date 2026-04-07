"""Live OpenAI-backed tests for LLM use cases."""

from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
import pytest

from air_platform.errors import DataNotFoundError
from air_platform.ingestion.models import (
    CleaningSummary,
    MissingStrategy,
    ProcessedDataset,
    ProcessingConfig,
    QualityReport,
    TimeRange,
)
from air_platform.llm.openai_provider import OpenAIProvider
from air_platform.llm.schemas import MetricAggregation, SupportedMetric
from air_platform.llm.use_cases import (
    AnswerNLQueryUseCase,
    GenerateDataQualityReportUseCase,
    SummarizeStationHealthUseCase,
)
from air_platform.metrics.models import MetricQuery, MetricResult

pytestmark = pytest.mark.openai_live

_NOW = datetime(2024, 2, 1, 6, 0, 0, tzinfo=UTC)
_NL_QUERY = "What is the mean of average_pressure_bar for station station-1?"


def _make_metric(
    station_id: str = "station-1",
    device_id: str = "device-1",
    metric_name: str = "average_pressure_bar",
    metric_value: float = 8.5,
) -> MetricResult:
    return MetricResult(
        station_id=station_id,
        device_id=device_id,
        metric_name=metric_name,
        metric_value=metric_value,
        unit="bar",
        window_start=datetime(2024, 2, 1, 0, 0, tzinfo=UTC),
        window_end=datetime(2024, 2, 1, 6, 0, tzinfo=UTC),
        computed_at=_NOW,
        resample_frequency="15min",
        missing_strategy="fill",
    )


class StubMetricRepository:
    def __init__(self, metrics: list[MetricResult]) -> None:
        self._metrics = metrics
        self.queries: list[MetricQuery] = []

    def save_metric_results(self, results: list[MetricResult]) -> None:  # pragma: no cover
        raise NotImplementedError

    def get_metric_results(self, query: MetricQuery) -> list[MetricResult]:
        self.queries.append(query)
        return list(self._metrics)


class StubPipeline:
    def __init__(self, dataset: ProcessedDataset) -> None:
        self._dataset = dataset
        self.configs: list[ProcessingConfig] = []

    def run(self, config: ProcessingConfig) -> ProcessedDataset:
        self.configs.append(config)
        return self._dataset


def _make_processed_dataset() -> ProcessedDataset:
    quality_report = QualityReport(
        total_rows_read=100,
        total_rows_after_cleaning=98,
        column_missing_pct={"discharge_pressure": 2.0},
        out_of_range_counts={},
        malformed_value_counts={},
        timestamp_gaps=[],
        flatline_periods=[],
        warnings=["One pressure value was missing and filled during cleaning."],
    )
    cleaning_summary = CleaningSummary(
        strategy=MissingStrategy.FILL,
        rows_before_cleaning=100,
        rows_after_cleaning=98,
        rows_after_resampling=12,
        malformed_values_coerced=0,
        out_of_range_values_nullified=0,
    )
    return ProcessedDataset(
        station_id="station-1",
        processed_data=pd.DataFrame(),
        time_range=TimeRange(start=None, end=None),
        resample_frequency="15min",
        quality_report=quality_report,
        cleaning_summary=cleaning_summary,
    )


class TestSummarizeStationHealth:
    def test_returns_summary_and_metrics(self, live_openai_provider: OpenAIProvider) -> None:
        repo = StubMetricRepository(
            [_make_metric(), _make_metric(metric_name="peak_pressure_bar", metric_value=9.2)]
        )
        use_case = SummarizeStationHealthUseCase(
            metric_repository=repo,
            llm=live_openai_provider,
        )

        result = use_case.execute("station-1")

        assert result.summary is not None
        assert result.summary.strip()
        assert result.llm_failed is False
        assert len(result.metrics) == 2
        assert repo.queries[0].station_id == "station-1"

    def test_raises_data_not_found_when_no_metrics(
        self,
        live_openai_provider: OpenAIProvider,
    ) -> None:
        repo = StubMetricRepository([])
        use_case = SummarizeStationHealthUseCase(
            metric_repository=repo,
            llm=live_openai_provider,
        )

        with pytest.raises(DataNotFoundError):
            use_case.execute("unknown-station")


class TestAnswerNLQuery:
    def test_parses_question_and_returns_deterministic_aggregate(
        self,
        live_openai_provider: OpenAIProvider,
    ) -> None:
        repo = StubMetricRepository(
            [_make_metric(metric_value=8.0), _make_metric(metric_value=9.0)]
        )
        use_case = AnswerNLQueryUseCase(metric_repository=repo, llm=live_openai_provider)

        result = use_case.execute(_NL_QUERY)

        assert result.original_question == _NL_QUERY
        assert result.parsed_query.station_id == "station-1"
        assert result.parsed_query.metric_name == SupportedMetric.AVERAGE_PRESSURE_BAR
        assert result.parsed_query.aggregation == MetricAggregation.MEAN
        assert result.aggregate_value == pytest.approx(8.5)
        assert result.natural_language_answer is not None
        assert result.natural_language_answer.strip()
        assert len(repo.queries) == 1

    def test_needs_clarification_for_unsupported_metric(
        self,
        live_openai_provider: OpenAIProvider,
    ) -> None:
        repo = StubMetricRepository([_make_metric()])
        use_case = AnswerNLQueryUseCase(metric_repository=repo, llm=live_openai_provider)

        result = use_case.execute("What is the mean of humidity for station station-1?")

        assert result.parsed_query.needs_clarification is True
        assert result.aggregate_value is None
        assert result.warning is not None
        assert repo.queries == []

    def test_empty_metric_results_yield_none_aggregate(
        self,
        live_openai_provider: OpenAIProvider,
    ) -> None:
        repo = StubMetricRepository([])
        use_case = AnswerNLQueryUseCase(metric_repository=repo, llm=live_openai_provider)

        result = use_case.execute(_NL_QUERY)

        assert result.parsed_query.metric_name == SupportedMetric.AVERAGE_PRESSURE_BAR
        assert result.aggregate_value is None
        assert result.metric_results == []
        assert result.natural_language_answer is None


class TestGenerateDataQualityReport:
    def test_returns_report_and_structured_findings(
        self,
        live_openai_provider: OpenAIProvider,
    ) -> None:
        pipeline = StubPipeline(_make_processed_dataset())
        use_case = GenerateDataQualityReportUseCase(
            pipeline=pipeline,
            llm=live_openai_provider,
        )

        result = use_case.execute("station-1")

        assert len(pipeline.configs) == 1
        assert result.report is not None
        assert result.report.strip()
        assert result.llm_failed is False
        assert result.total_rows_read == 100
        assert result.total_rows_after_cleaning == 98
        assert result.column_missing_pct == {"discharge_pressure": 2.0}
