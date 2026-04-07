"""Metric definitions exposed by the metrics engine."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MetricDefinition:
    """Static metadata for a metric."""

    name: str
    unit: str
    description: str


METRIC_DEFINITIONS: dict[str, MetricDefinition] = {
    "active_duration_hours": MetricDefinition(
        name="active_duration_hours",
        unit="h",
        description="Total active duration per device based on motor_speed > active_rpm_threshold.",
    ),
    "active_ratio_pct": MetricDefinition(
        name="active_ratio_pct",
        unit="%",
        description="Active time percentage over the processed window.",
    ),
    "average_pressure_bar": MetricDefinition(
        name="average_pressure_bar",
        unit="bar",
        description="Average discharge pressure over the processed window.",
    ),
    "peak_pressure_bar": MetricDefinition(
        name="peak_pressure_bar",
        unit="bar",
        description="Peak discharge pressure over the processed window.",
    ),
    "mean_specific_power_kw_per_m3h": MetricDefinition(
        name="mean_specific_power_kw_per_m3h",
        unit="kW/(m3/h)",
        description="Mean specific power using rows with positive flow.",
    ),
    "cycle_count": MetricDefinition(
        name="cycle_count",
        unit="count",
        description="Inactive-to-active transitions in the selected window.",
    ),
    "total_flow_volume_m3": MetricDefinition(
        name="total_flow_volume_m3",
        unit="m3",
        description="Integrated air flow volume across the processed window.",
    ),
}
