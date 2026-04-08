"""Typed errors for the event-driven ingestion pipeline."""

from __future__ import annotations


class EventError(Exception):
    """Base class for event processing errors."""


class MalformedEventError(EventError):
    """Raised when an event cannot be deserialized or is structurally invalid.

    Examples: missing required fields, completely corrupt payload.
    """


class EventValidationError(EventError):
    """Raised when a structurally valid event fails business validation.

    Examples: wrong event_type, unreadable timestamp.
    """


class EventProcessingError(EventError):
    """Raised when domain processing of a valid event fails.

    Examples: schema load failure during handler init, unexpected runtime error.
    """


class TransportError(EventError):
    """Raised for transport-layer failures (e.g., connection lost)."""
