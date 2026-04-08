"""Application-level dependency container for Challenge 3.

A single ``AppContainer`` instance is created at startup, stored on
``app.state.container``, and shared between the background consumer thread
and the FastAPI request handlers. All Challenge 3 repositories live here.

The container is the *only* place where in-memory transport, repositories,
handler, and consumer are wired together.
"""

from __future__ import annotations

import logging
import queue
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from air_platform.ingestion.consumer import ConsumerRunner
from air_platform.ingestion.handler import EventHandler
from air_platform.repositories.errors import InMemoryErrorRepository
from air_platform.repositories.metrics_aggregate import InMemoryMetricsAggregateRepository
from air_platform.repositories.processing_status import InMemoryProcessingStatusRepository
from air_platform.transport.in_memory_queue import InMemoryQueueTransport

_logger = logging.getLogger(__name__)


@dataclass
class AppContainer:
    """Shared singleton holding all Challenge 3 runtime components.

    Create via ``AppContainer.build(schema_path)`` and store on
    ``app.state.container`` in the FastAPI lifespan.
    """

    event_queue: queue.Queue[dict[str, Any] | None]
    transport: InMemoryQueueTransport
    metrics_aggregate_repo: InMemoryMetricsAggregateRepository
    status_repo: InMemoryProcessingStatusRepository
    error_repo: InMemoryErrorRepository
    consumer: ConsumerRunner

    @classmethod
    def build(
        cls,
        schema_path: str | Path,
        consumer_error_cap: int = 100,
    ) -> AppContainer:
        """Construct all components and wire them together."""
        q: queue.Queue[dict[str, Any] | None] = queue.Queue()
        transport = InMemoryQueueTransport(q)

        metrics_repo = InMemoryMetricsAggregateRepository()
        status_repo = InMemoryProcessingStatusRepository()
        error_repo = InMemoryErrorRepository(max_errors=consumer_error_cap)

        handler = EventHandler(
            schema_path=schema_path,
            metrics_aggregate_repo=metrics_repo,
            status_repo=status_repo,
        )
        consumer = ConsumerRunner(
            transport=transport,
            handler=handler,
            status_repo=status_repo,
            error_repo=error_repo,
        )

        _logger.info("AppContainer built with schema: %s", schema_path)
        return cls(
            event_queue=q,
            transport=transport,
            metrics_aggregate_repo=metrics_repo,
            status_repo=status_repo,
            error_repo=error_repo,
            consumer=consumer,
        )

    def start_consumer(self) -> None:
        """Start the background consumer thread."""
        self.consumer.start_background()

    def stop_consumer(self) -> None:
        """Stop the background consumer thread."""
        self.consumer.stop()
