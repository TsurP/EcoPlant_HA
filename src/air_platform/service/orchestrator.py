"""Service-layer orchestration for processing requests."""

from __future__ import annotations

from dataclasses import dataclass

from air_platform.ingestion.models import ProcessedDataset, ProcessingConfig
from air_platform.ingestion.pipeline import IngestionPipeline
from air_platform.metrics.engine import MetricsEngine
from air_platform.metrics.models import MetricConfig, MetricQuery, MetricResult
from air_platform.storage.base import MetricResultRepository


@dataclass(frozen=True)
class StationProcessingSummary:
    """Result of a process-station operation."""

    dataset: ProcessedDataset
    metrics: list[MetricResult]

    @property
    def metrics_saved(self) -> int:
        return len(self.metrics)


class StationProcessingService:
    """Application service coordinating ingestion, metrics, and storage."""

    def __init__(
        self,
        pipeline: IngestionPipeline,
        metric_repository: MetricResultRepository,
        default_metric_config: MetricConfig,
    ) -> None:
        self.pipeline = pipeline
        self.metric_repository = metric_repository
        self.default_metric_config = default_metric_config

    def process_station(
        self,
        processing_config: ProcessingConfig,
        metric_config: MetricConfig | None = None,
    ) -> StationProcessingSummary:
        dataset = self.pipeline.run(processing_config)
        engine = MetricsEngine(metric_config or self.default_metric_config)
        metrics = engine.compute(dataset)
        self.metric_repository.save_metric_results(metrics)
        return StationProcessingSummary(dataset=dataset, metrics=metrics)

    def get_metrics(self, query: MetricQuery) -> list[MetricResult]:
        return self.metric_repository.get_metric_results(query)
