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

    Important: ``queue.Queue`` is not cross-process. The producer and the API
    must run in the **same Python process** and share the same queue instance.
    Pass the shared queue via the ``event_queue`` argument of ``build()``.
    See ``run_with_producer.py`` for an example of correct in-process wiring.
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
        event_queue: queue.Queue[dict[str, Any] | None] | None = None,
    ) -> AppContainer:
        """Construct all components and wire them together.

        Args:
            schema_path: Path to the sensor JSON schema file.
            consumer_error_cap: Maximum number of processing errors to retain.
            event_queue: Optional pre-created ``queue.Queue`` to use as the
                event transport.  Pass this when you want to share the same
                queue with an external producer running in the same process
                (e.g. ``run_with_producer.py``).  If *None*, a fresh private
                queue is created — useful for the standalone API server where
                no producer is wired in.
        """
        q: queue.Queue[dict[str, Any] | None] = (
            event_queue if event_queue is not None else queue.Queue()
        )
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
