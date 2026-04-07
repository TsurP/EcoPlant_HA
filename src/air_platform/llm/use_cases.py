"""Application-layer use cases for LLM-powered features.

Each use case:
- Depends on existing deterministic services / repositories.
- Calls the LLM only for language generation / structured extraction.
- Returns structured data **plus** any generated text.
- Degrades gracefully: if the LLM fails, structured data is still returned.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from air_platform.errors import DataNotFoundError, LLMError
from air_platform.ingestion.models import ProcessedDataset, ProcessingConfig, QualityReport
from air_platform.llm import prompts
from air_platform.llm.provider import LLMProvider
from air_platform.llm.schemas import MetricAggregation, StructuredMetricQuery
from air_platform.metrics.models import MetricQuery, MetricResult
from air_platform.storage.base import MetricResultRepository

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal protocol — allows test stubs without depending on IngestionPipeline
# ---------------------------------------------------------------------------


class _PipelineLike(Protocol):
    def run(self, config: ProcessingConfig) -> ProcessedDataset: ...


# ---------------------------------------------------------------------------
# Result dataclasses (domain layer — no Pydantic, no FastAPI)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StationSummaryResult:
    """Result of the station-health summarisation use case."""

    station_id: str
    start_time: datetime | None
    end_time: datetime | None
    summary: str | None
    metrics: list[MetricResult]
    llm_failed: bool = False
    warning: str | None = None


@dataclass(frozen=True)
class NLQueryResult:
    """Result of the natural-language query use case."""

    original_question: str
    parsed_query: StructuredMetricQuery
    metric_results: list[MetricResult]
    aggregate_value: float | None
    natural_language_answer: str | None
    llm_rendering_failed: bool = False
    warning: str | None = None


@dataclass(frozen=True)
class DQReportResult:
    """Result of the data-quality report generation use case."""

    station_id: str
    start_time: datetime | None
    end_time: datetime | None
    report: str | None
    total_rows_read: int
    total_rows_after_cleaning: int
    column_missing_pct: dict[str, float]
    out_of_range_counts: dict[str, int]
    malformed_value_counts: dict[str, int]
    gap_count: int
    flatline_count: int
    warnings: list[str]
    llm_failed: bool = False
    llm_warning: str | None = None


# ---------------------------------------------------------------------------
# Use case 1 — Summarise station health
# ---------------------------------------------------------------------------


class SummarizeStationHealthUseCase:
    """Fetch deterministic metrics for a station and generate a plain-English summary."""

    def __init__(
        self,
        metric_repository: MetricResultRepository,
        llm: LLMProvider,
    ) -> None:
        self._repo = metric_repository
        self._llm = llm

    def execute(
        self,
        station_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> StationSummaryResult:
        metrics = self._repo.get_metric_results(
            MetricQuery(
                station_id=station_id,
                start_time=start_time,
                end_time=end_time,
            )
        )

        if not metrics:
            raise DataNotFoundError(
                f"No computed metrics found for station '{station_id}'. "
                "Run POST /stations/{station_id}/process first."
            )

        period = _format_period(start_time, end_time)
        snapshot = _build_metrics_snapshot(metrics)

        summary, llm_failed, warning = _try_generate_text(
            self._llm,
            system_prompt=prompts.STATION_HEALTH_SYSTEM,
            user_content=prompts.station_health_user(station_id, period, snapshot),
            fallback_warning="LLM summarisation failed; structured metrics are still returned.",
        )

        return StationSummaryResult(
            station_id=station_id,
            start_time=start_time,
            end_time=end_time,
            summary=summary,
            metrics=metrics,
            llm_failed=llm_failed,
            warning=warning,
        )


# ---------------------------------------------------------------------------
# Use case 2 — Answer natural-language metric query
# ---------------------------------------------------------------------------


class AnswerNLQueryUseCase:
    """Parse a natural-language question, execute it deterministically, optionally phrase it."""

    def __init__(
        self,
        metric_repository: MetricResultRepository,
        llm: LLMProvider,
    ) -> None:
        self._repo = metric_repository
        self._llm = llm

    def execute(self, question: str) -> NLQueryResult:
        # Step 1: parse the question into a structured query via LLM.
        try:
            parsed = self._llm.generate_structured(
                system_prompt=prompts.NL_QUERY_SYSTEM,
                user_content=prompts.nl_query_user(question),
                schema=StructuredMetricQuery,
            )
        except LLMError as exc:
            logger.warning("nl_query parsing failed — returning clarification response: %s", exc)
            fallback = StructuredMetricQuery(
                needs_clarification=True,
                clarification_message=(
                    "The query parser is temporarily unavailable. Please try again shortly."
                ),
            )
            return NLQueryResult(
                original_question=question,
                parsed_query=fallback,
                metric_results=[],
                aggregate_value=None,
                natural_language_answer=None,
                llm_rendering_failed=True,
                warning=fallback.clarification_message,
            )

        logger.info(
            "nl_query parsed station=%s metric=%s needs_clarification=%s",
            parsed.station_id,
            parsed.metric_name,
            parsed.needs_clarification,
        )

        # Step 2: return early if clarification is needed.
        if parsed.needs_clarification:
            return NLQueryResult(
                original_question=question,
                parsed_query=parsed,
                metric_results=[],
                aggregate_value=None,
                natural_language_answer=None,
                warning=parsed.clarification_message,
            )

        # Step 3: execute the query deterministically.
        metric_results = self._repo.get_metric_results(
            MetricQuery(
                station_id=parsed.station_id,
                device_id=parsed.device_id,
                metric_name=parsed.metric_name,
            )
        )

        aggregate_value = _aggregate(metric_results, parsed.aggregation)

        # Step 4: optionally phrase the result in English.
        nl_answer: str | None = None
        llm_rendering_failed = False
        rendering_warning: str | None = None

        if aggregate_value is not None:
            result_summary = (
                f"metric={parsed.metric_name} "
                f"aggregation={parsed.aggregation} "
                f"value={aggregate_value}"
            )
            nl_answer, llm_rendering_failed, rendering_warning = _try_generate_text(
                self._llm,
                system_prompt=prompts.NL_ANSWER_SYSTEM,
                user_content=prompts.nl_answer_user(question, result_summary),
                fallback_warning="LLM phrasing failed; numeric result is still returned.",
            )

        return NLQueryResult(
            original_question=question,
            parsed_query=parsed,
            metric_results=metric_results,
            aggregate_value=aggregate_value,
            natural_language_answer=nl_answer,
            llm_rendering_failed=llm_rendering_failed,
            warning=rendering_warning,
        )


# ---------------------------------------------------------------------------
# Use case 3 — Generate data quality report
# ---------------------------------------------------------------------------


class GenerateDataQualityReportUseCase:
    """Run the ingestion pipeline and generate a plain-English quality report."""

    def __init__(
        self,
        pipeline: _PipelineLike,
        llm: LLMProvider,
    ) -> None:
        self._pipeline: _PipelineLike = pipeline
        self._llm = llm

    def execute(
        self,
        station_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> DQReportResult:
        config = ProcessingConfig(
            station_id=station_id,
            start_time=start_time,
            end_time=end_time,
        )
        dataset = self._pipeline.run(config)
        qr = dataset.quality_report

        period = _format_period(start_time, end_time)
        findings_text = _build_quality_findings(qr)

        report, llm_failed, llm_warning = _try_generate_text(
            self._llm,
            system_prompt=prompts.DQ_REPORT_SYSTEM,
            user_content=prompts.dq_report_user(station_id, period, findings_text),
            fallback_warning=(
                "LLM report generation failed; structured findings are still returned."
            ),
        )

        return DQReportResult(
            station_id=station_id,
            start_time=start_time,
            end_time=end_time,
            report=report,
            total_rows_read=qr.total_rows_read,
            total_rows_after_cleaning=qr.total_rows_after_cleaning,
            column_missing_pct=qr.column_missing_pct,
            out_of_range_counts=qr.out_of_range_counts,
            malformed_value_counts=qr.malformed_value_counts,
            gap_count=len(qr.timestamp_gaps),
            flatline_count=len(qr.flatline_periods),
            warnings=qr.warnings,
            llm_failed=llm_failed,
            llm_warning=llm_warning,
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _try_generate_text(
    llm: LLMProvider,
    system_prompt: str,
    user_content: str,
    fallback_warning: str,
) -> tuple[str | None, bool, str | None]:
    """Call LLM and return (text, failed, warning). Never raises."""
    try:
        text = llm.generate_text(system_prompt=system_prompt, user_content=user_content)
        return text, False, None
    except LLMError as exc:
        logger.warning("llm.generate_text degraded: %s", exc)
        return None, True, fallback_warning


def _build_metrics_snapshot(metrics: list[MetricResult]) -> str:
    """Format metrics as a compact JSON-like text for the LLM prompt."""
    rows: list[dict[str, object]] = []
    for m in metrics:
        rows.append(
            {
                "device_id": m.device_id,
                "metric_name": m.metric_name,
                "metric_value": round(m.metric_value, 4),
                "unit": m.unit,
                "window_start": m.window_start.isoformat(),
                "window_end": m.window_end.isoformat(),
            }
        )
    return json.dumps(rows, indent=2)


def _build_quality_findings(qr: QualityReport) -> str:
    """Format quality report fields as structured text for the LLM prompt."""
    lines = [
        f"total_rows_read: {qr.total_rows_read}",
        f"total_rows_after_cleaning: {qr.total_rows_after_cleaning}",
        "column_missing_pct: " + json.dumps(qr.column_missing_pct),
        "out_of_range_counts: " + json.dumps(qr.out_of_range_counts),
        "malformed_value_counts: " + json.dumps(qr.malformed_value_counts),
        f"timestamp_gaps: {len(qr.timestamp_gaps)} detected",
        f"flatline_periods: {len(qr.flatline_periods)} detected",
    ]
    if qr.warnings:
        lines.append("warnings: " + "; ".join(qr.warnings))
    return "\n".join(lines)


def _aggregate(metrics: list[MetricResult], aggregation: MetricAggregation) -> float | None:
    """Aggregate metric values deterministically according to *aggregation*."""
    if not metrics:
        return None
    values = [m.metric_value for m in metrics]
    if aggregation == MetricAggregation.MEAN:
        return sum(values) / len(values)
    if aggregation == MetricAggregation.MAX:
        return max(values)
    if aggregation == MetricAggregation.SUM:
        return sum(values)
    if aggregation == MetricAggregation.LATEST:
        latest = max(metrics, key=lambda m: m.computed_at)
        return latest.metric_value
    return None  # pragma: no cover


def _format_period(start: datetime | None, end: datetime | None) -> str:
    start_str = start.isoformat() if start else "beginning"
    end_str = end.isoformat() if end else "now"
    return f"{start_str} to {end_str}"
