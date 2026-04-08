"""In-memory repository for consumer processing status."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime


@dataclass
class ProcessingStatus:
    """Snapshot of the consumer's current state and counters."""

    consumer_running: bool = False
    events_consumed: int = 0
    events_processed_successfully: int = 0
    events_malformed: int = 0
    events_failed: int = 0
    last_event_timestamp: datetime | None = None
    last_success_timestamp: datetime | None = None
    last_error_timestamp: datetime | None = None
    queue_depth: int | None = None


class InMemoryProcessingStatusRepository:
    """Thread-safe store for consumer status counters and timestamps."""

    def __init__(self) -> None:
        self._status: ProcessingStatus = ProcessingStatus()
        self._lock = threading.Lock()

    def get_status(self) -> ProcessingStatus:
        """Return a snapshot copy of the current status."""
        with self._lock:
            return ProcessingStatus(
                consumer_running=self._status.consumer_running,
                events_consumed=self._status.events_consumed,
                events_processed_successfully=self._status.events_processed_successfully,
                events_malformed=self._status.events_malformed,
                events_failed=self._status.events_failed,
                last_event_timestamp=self._status.last_event_timestamp,
                last_success_timestamp=self._status.last_success_timestamp,
                last_error_timestamp=self._status.last_error_timestamp,
                queue_depth=self._status.queue_depth,
            )

    def set_running(self, running: bool) -> None:
        with self._lock:
            self._status.consumer_running = running

    def increment_consumed(self, event_timestamp: datetime | None = None) -> None:
        with self._lock:
            self._status.events_consumed += 1
            if event_timestamp is not None:
                self._status.last_event_timestamp = event_timestamp

    def record_success(self, timestamp: datetime | None = None) -> None:
        now = timestamp or _utc_now()
        with self._lock:
            self._status.events_processed_successfully += 1
            self._status.last_success_timestamp = now

    def increment_malformed(self, timestamp: datetime | None = None) -> None:
        now = timestamp or _utc_now()
        with self._lock:
            self._status.events_malformed += 1
            self._status.last_error_timestamp = now

    def increment_failed(self, timestamp: datetime | None = None) -> None:
        now = timestamp or _utc_now()
        with self._lock:
            self._status.events_failed += 1
            self._status.last_error_timestamp = now

    def set_queue_depth(self, depth: int | None) -> None:
        with self._lock:
            self._status.queue_depth = depth


def _utc_now() -> datetime:
    from datetime import UTC

    return datetime.now(UTC)
