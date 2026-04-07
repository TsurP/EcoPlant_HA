"""Typed metric models."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MetricConfig:
    """Configuration values used by the metrics engine."""

    active_rpm_threshold: int = 500
    specific_power_flow_threshold: float = 1.0


@dataclass(frozen=True)
class MetricResult:
    """Single computed metric row."""

    station_id: str
    device_id: str
    metric_name: str
    metric_value: float
    unit: str
    window_start: datetime
    window_end: datetime
    computed_at: datetime
    resample_frequency: str
    missing_strategy: str


@dataclass(frozen=True)
class MetricQuery:
    """Filters for retrieving stored metrics."""

    station_id: str | None = None
    device_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    metric_name: str | None = None
