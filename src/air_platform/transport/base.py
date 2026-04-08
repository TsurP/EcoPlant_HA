"""Transport protocol and message model for event consumers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class TransportMessage:
    """A message received from any transport layer."""

    id: str
    payload: dict[str, Any]


@runtime_checkable
class MessageTransport(Protocol):
    """Protocol for pluggable event transport adapters.

    Implementations may back this with queue.Queue, Redis Streams,
    Pub/Sub, Kafka, etc. The consumer depends only on this interface.
    """

    @property
    def sentinel_received(self) -> bool:
        """True once the producer has signalled end-of-stream.

        For transports with no end-of-stream concept (e.g. Kafka) this
        should always return False, keeping the consumer running until
        stop() is called explicitly.
        """
        ...

    def receive(self) -> TransportMessage | None:
        """Return the next available message, or None if none available right now."""
        ...

    def receive_blocking(self, timeout_s: float) -> TransportMessage | None:
        """Block up to *timeout_s* seconds for the next message.

        Returns the message if one arrives within the timeout, or ``None`` if
        the queue is still empty after the timeout expires.  Implementations
        that do not support blocking may fall back to a single non-blocking
        ``receive()`` call.
        """
        ...

    def ack(self, message: TransportMessage) -> None:
        """Acknowledge successful processing of a message."""
        ...

    def reject(self, message: TransportMessage, reason: str) -> None:
        """Reject a message after a processing failure."""
        ...

    def size(self) -> int | None:
        """Return approximate queue depth, or None if unavailable."""
        ...
