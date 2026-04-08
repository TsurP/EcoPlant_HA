"""Consumer loop: pulls messages from a transport and routes them through the handler.

The consumer never crashes due to a bad event. Each failure is classified,
recorded, and rejected before the loop continues.

Architecture:
  Transport → ConsumerRunner.run_loop()
    → handler.handle(msg)        → success: ack + record_success
    → MalformedEventError        → record + reject
    → EventValidationError       → record + reject
    → EventProcessingError       → record + reject
    → unexpected Exception       → record + reject (safety net)
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from air_platform.ingestion.errors import (
    EventProcessingError,
    EventValidationError,
    MalformedEventError,
)
from air_platform.ingestion.handler import EventHandler
from air_platform.repositories.errors import InMemoryErrorRepository, ProcessingError
from air_platform.repositories.processing_status import InMemoryProcessingStatusRepository
from air_platform.transport.base import MessageTransport, TransportMessage

_logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 0.01  # Sleep between empty-queue polls


class ConsumerRunner:
    """Drives the consume loop for a single transport/handler pair.

    Usage (background thread)::

        runner = ConsumerRunner(transport, handler, status_repo, error_repo)
        runner.start_background()
        # ... app runs ...
        runner.stop()

    Usage (synchronous, useful in tests)::

        runner.run_until_empty()
    """

    def __init__(
        self,
        transport: MessageTransport,
        handler: EventHandler,
        status_repo: InMemoryProcessingStatusRepository,
        error_repo: InMemoryErrorRepository,
    ) -> None:
        self._transport = transport
        self._handler = handler
        self._status_repo = status_repo
        self._error_repo = error_repo
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def start_background(self) -> None:
        """Start the consume loop in a daemon background thread."""
        if self._thread is not None and self._thread.is_alive():
            return  # Already running
        self._stop_event.clear()
        self._thread = threading.Thread(target=self.run_loop, daemon=True, name="consumer-loop")
        self._status_repo.set_running(True)
        self._thread.start()
        _logger.info("Consumer loop started in background thread.")

    def stop(self, timeout: float = 5.0) -> None:
        """Signal the loop to stop and wait for the thread to exit."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        self._status_repo.set_running(False)
        _logger.info("Consumer loop stopped.")

    def run_loop(self) -> None:
        """Main consume loop: runs until stop() is called or end-of-stream sentinel received."""
        while not self._stop_event.is_set():
            msg = self._transport.receive()
            if msg is None:
                if self._transport.sentinel_received:
                    # Producer finished; no more messages will arrive — exit cleanly.
                    break
                time.sleep(_POLL_INTERVAL_SECONDS)
                continue
            self._process_message(msg)

        self._status_repo.set_running(False)

    def run_until_empty(self) -> None:
        """Process all currently available messages and return when the queue is empty.

        Useful for synchronous testing without background threads.
        """
        while True:
            msg = self._transport.receive()
            if msg is None:
                break
            self._process_message(msg)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _process_message(self, msg: TransportMessage) -> None:
        """Process one message, recording success or failure in repositories."""
        now = datetime.now(UTC)
        event_ts = _extract_event_timestamp(msg.payload)
        self._status_repo.increment_consumed(event_timestamp=event_ts)
        self._status_repo.set_queue_depth(self._transport.size())

        try:
            self._handler.handle(msg)
        except MalformedEventError as exc:
            self._record_error("malformed_event", exc, msg.id, now)
            self._status_repo.increment_malformed(now)
            self._transport.reject(msg, reason=str(exc))
            return
        except EventValidationError as exc:
            self._record_error("validation_error", exc, msg.id, now)
            self._status_repo.increment_failed(now)
            self._transport.reject(msg, reason=str(exc))
            return
        except EventProcessingError as exc:
            self._record_error("processing_error", exc, msg.id, now)
            self._status_repo.increment_failed(now)
            self._transport.reject(msg, reason=str(exc))
            return
        except Exception as exc:  # safety net — consumer must never crash
            _logger.exception("Unexpected error processing message %s", msg.id)
            self._record_error("unexpected_error", exc, msg.id, now)
            self._status_repo.increment_failed(now)
            self._transport.reject(msg, reason=str(exc))
            return

        self._transport.ack(msg)
        self._status_repo.record_success(now)

    def _record_error(
        self,
        error_type: str,
        exc: Exception,
        event_id: str,
        occurred_at: datetime,
    ) -> None:
        error = ProcessingError(
            error_id=str(uuid4()),
            error_type=error_type,
            message=str(exc),
            event_id=event_id or None,
            occurred_at=occurred_at,
            detail=type(exc).__name__,
        )
        self._error_repo.append(error)
        _logger.warning("Event %s rejected [%s]: %s", event_id, error_type, exc)


def _extract_event_timestamp(payload: dict[str, Any]) -> datetime | None:
    """Parse the event's own timestamp from its payload, if present."""
    raw = payload.get("timestamp")
    if not isinstance(raw, str):
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None
