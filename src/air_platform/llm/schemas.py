"""Structured query schema for the natural-language query endpoint.

The LLM is instructed to produce a *StructuredMetricQuery*. The application
then validates it and executes the query deterministically — the LLM never
performs computation or accesses raw data directly.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class SupportedMetric(StrEnum):
    """Metrics the platform currently computes."""

    ACTIVE_DURATION_HOURS = "active_duration_hours"
    ACTIVE_RATIO_PCT = "active_ratio_pct"
    AVERAGE_PRESSURE_BAR = "average_pressure_bar"
    PEAK_PRESSURE_BAR = "peak_pressure_bar"
    MEAN_SPECIFIC_POWER = "mean_specific_power_kw_per_m3h"
    CYCLE_COUNT = "cycle_count"
    TOTAL_FLOW_VOLUME_M3 = "total_flow_volume_m3"


class MetricAggregation(StrEnum):
    """Cross-result aggregation strategy for a metric query."""

    MEAN = "mean"
    MAX = "max"
    SUM = "sum"
    LATEST = "latest"


class StructuredMetricQuery(BaseModel):
    """Bounded, validated metric query produced by parsing a natural-language question.

    The LLM populates this schema; the application executes it deterministically.
    Any field the LLM cannot determine from the question must be left null.
    """

    station_id: str | None = Field(
        default=None, description="Station identifier extracted from the question."
    )
    device_id: str | None = Field(
        default=None, description="Specific device within the station, if mentioned."
    )
    metric_name: SupportedMetric | None = Field(
        default=None, description="One of the supported metric names."
    )
    aggregation: MetricAggregation = Field(
        default=MetricAggregation.MEAN,
        description="How to aggregate across matching metric rows.",
    )
    start_time: str | None = Field(
        default=None, description="ISO-8601 start of the query window, or null."
    )
    end_time: str | None = Field(
        default=None, description="ISO-8601 end of the query window, or null."
    )
    needs_clarification: bool = Field(
        default=False,
        description="True when the question is ambiguous or uses unsupported features.",
    )
    clarification_message: str | None = Field(
        default=None,
        description="Plain-English explanation of what needs to be clarified.",
    )
