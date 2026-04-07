"""Metric computation independent from FastAPI."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pandas as pd

from air_platform.ingestion.models import ProcessedDataset
from air_platform.metrics.definitions import METRIC_DEFINITIONS
from air_platform.metrics.models import MetricConfig, MetricResult


class MetricsEngine:
    """Compute operational metrics from a processed dataset."""

    def __init__(self, config: MetricConfig | None = None) -> None:
        self.config = config or MetricConfig()

    def compute(self, dataset: ProcessedDataset) -> list[MetricResult]:
        results: list[MetricResult] = []
        computed_at = datetime.now(UTC)

        for device_id, group in dataset.processed_data.groupby("device_id"):
            ordered = group.sort_values("timestamp").reset_index(drop=True)
            if ordered.empty:
                continue

            timestamps = _coerce_timestamps(ordered["timestamp"].tolist())
            interval_hours = _infer_interval_hours(
                timestamps,
                dataset.resample_frequency,
            )
            active_mask = ordered["motor_speed"].fillna(0) > self.config.active_rpm_threshold
            flow_mask = (
                ordered["air_flow_rate"].fillna(0) > self.config.specific_power_flow_threshold
            )

            window_start = timestamps[0].to_pydatetime()
            window_end = timestamps[-1].to_pydatetime()

            metric_values = {
                "active_duration_hours": float(active_mask.sum()) * interval_hours,
                "active_ratio_pct": float(active_mask.mean() * 100.0),
                "average_pressure_bar": _mean_or_zero(ordered["discharge_pressure"]),
                "peak_pressure_bar": _max_or_zero(ordered["discharge_pressure"]),
                "mean_specific_power_kw_per_m3h": _mean_or_zero(
                    ordered.loc[flow_mask, "power_consumption"]
                    / ordered.loc[flow_mask, "air_flow_rate"]
                ),
                "cycle_count": float(_count_cycles(active_mask)),
                "total_flow_volume_m3": float(
                    ordered["air_flow_rate"].fillna(0).sum() * interval_hours
                ),
            }

            for metric_name, metric_value in metric_values.items():
                definition = METRIC_DEFINITIONS[metric_name]
                results.append(
                    MetricResult(
                        station_id=dataset.station_id,
                        device_id=str(device_id),
                        metric_name=metric_name,
                        metric_value=metric_value,
                        unit=definition.unit,
                        window_start=window_start,
                        window_end=window_end,
                        computed_at=computed_at,
                        resample_frequency=dataset.resample_frequency,
                        missing_strategy=dataset.cleaning_summary.strategy.value,
                    )
                )

        return results


def _infer_interval_hours(timestamps: Sequence[pd.Timestamp], fallback_frequency: str) -> float:
    if len(timestamps) > 1:
        deltas = [
            timestamps[index] - timestamps[index - 1]
            for index in range(1, len(timestamps))
            if timestamps[index] > timestamps[index - 1]
        ]
        if deltas:
            median_seconds = sorted(delta.total_seconds() for delta in deltas)[len(deltas) // 2]
            return float(median_seconds / 3600.0)
    return float(pd.to_timedelta(fallback_frequency).total_seconds() / 3600.0)


def _mean_or_zero(series: pd.Series) -> float:
    cleaned = series.dropna()
    if cleaned.empty:
        return 0.0
    return float(cleaned.mean())


def _max_or_zero(series: pd.Series) -> float:
    cleaned = series.dropna()
    if cleaned.empty:
        return 0.0
    return float(cleaned.max())


def _count_cycles(active_mask: pd.Series) -> int:
    previous = active_mask.shift(1)
    transitions = active_mask & previous.eq(False)
    return int(transitions.sum())


def _coerce_timestamps(values: Sequence[object]) -> list[pd.Timestamp]:
    return [pd.Timestamp(str(value)) for value in values]
