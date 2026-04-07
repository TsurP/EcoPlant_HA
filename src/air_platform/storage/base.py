"""Repository interface for persisted metric results."""

from __future__ import annotations

from typing import Protocol

from air_platform.metrics.models import MetricQuery, MetricResult


class MetricResultRepository(Protocol):
    """Abstract metric store."""

    def save_metric_results(self, results: list[MetricResult]) -> None:
        """Persist a batch of metric results."""

    def get_metric_results(self, query: MetricQuery) -> list[MetricResult]:
        """Return metric results matching the query."""
