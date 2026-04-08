"""In-memory queue transport adapter backed by Python's queue.Queue.

Compatible with the SensorEventProducer in producer.py, which puts dict
payloads into the queue and sends ``None`` as an end-of-stream sentinel.
"""

from __future__ import annotations

import queue
from typing import Any

from air_platform.transport.base import TransportMessage


class InMemoryQueueTransport:
    """Transport adapter that wraps a Python ``queue.Queue``.

    The producer puts ``dict[str, Any]`` events and a final ``None`` sentinel.
    This adapter wraps each dict in a ``TransportMessage`` and marks the stream
    as done once the sentinel is received.
    """

    def __init__(self, q: queue.Queue[dict[str, Any] | None]) -> None:
        self._queue = q
        self._sentinel_received = False

    @property
    def sentinel_received(self) -> bool:
        """True once the producer has sent its end-of-stream ``None`` sentinel."""
        return self._sentinel_received

    def receive(self) -> TransportMessage | None:
        """Return next available message, or None if queue is currently empty."""
        try:
            raw = self._queue.get(block=False)
        except queue.Empty:
            return None

        if raw is None:
            # Sentinel: producer finished. Signal stream end to the consumer.
            self._sentinel_received = True
            return None

        event_id = str(raw.get("event_id", ""))
        return TransportMessage(id=event_id, payload=raw)

    def ack(self, message: TransportMessage) -> None:
        """No-op: simple Queue does not require explicit acknowledgement."""

    def reject(self, message: TransportMessage, reason: str) -> None:
        """No-op: rejected events are recorded at the consumer layer."""

    def size(self) -> int | None:
        """Return approximate queue depth."""
        return self._queue.qsize()
