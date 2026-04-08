"""In-memory repository for recent processing errors."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ProcessingError:
    """Record of a single event processing failure."""

    error_id: str
    error_type: str
    message: str
    event_id: str | None
    occurred_at: datetime
    detail: str | None = None


class InMemoryErrorRepository:
    """Thread-safe capped list of recent processing errors.

    Older entries are automatically evicted once ``max_errors`` is reached.
    """

    def __init__(self, max_errors: int = 100) -> None:
        self._errors: deque[ProcessingError] = deque(maxlen=max_errors)
        self._lock = threading.Lock()

    def append(self, error: ProcessingError) -> None:
        """Add an error to the recent list."""
        with self._lock:
            self._errors.append(error)

    def get_recent(self, limit: int = 50) -> list[ProcessingError]:
        """Return the most recent errors, newest last, up to ``limit``."""
        with self._lock:
            items = list(self._errors)
        return items[-limit:]
