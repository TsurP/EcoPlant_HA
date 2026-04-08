"""Event handler: parses raw transport messages and updates aggregate metrics.

Architecture:
  TransportMessage (raw dict)
  → parse_event()          → RawSensorEvent (structural)
  → map_to_sensor_reading() → SensorReading (internal domain)
  → _apply_range_validation()  → cleaned values (reuses schema ranges)
  → upsert_aggregate()         → repositories
"""

from __future__ import annotations

import logging
from collections import OrderedDict
from datetime import UTC, datetime
from pathlib import Path

from air_platform.ingestion.errors import (
    EventProcessingError,
    EventValidationError,
    MalformedEventError,
)
from air_platform.ingestion.event_models import SensorReading
from air_platform.ingestion.models import TableSchema
from air_platform.ingestion.parser import map_to_sensor_reading, parse_event
from air_platform.ingestion.schema_loader import load_schema
from air_platform.repositories.metrics_aggregate import InMemoryMetricsAggregateRepository
from air_platform.repositories.processing_status import InMemoryProcessingStatusRepository
from air_platform.transport.base import TransportMessage

_logger = logging.getLogger(__name__)

_BUCKETS = ("hour", "day")
# Maximum number of event IDs retained for deduplication.
# Oldest entries are evicted first, so memory is bounded.
_DEDUP_CACHE_MAX = 10_000


class EventHandler:
    """Handles a single transport message end-to-end.

    Responsibilities:
    - Parse and validate the raw payload
    - Apply schema-based range validation (reusing ColumnSchema.valid_range)
    - Update incremental aggregates per metric/bucket
    - Record success/failure in the status repository

    Raises:
        MalformedEventError: structural parse failure
        EventValidationError: business validation failure
        EventProcessingError: unexpected domain processing error
    """

    def __init__(
        self,
        schema_path: str | Path,
        metrics_aggregate_repo: InMemoryMetricsAggregateRepository,
        status_repo: InMemoryProcessingStatusRepository,
    ) -> None:
        try:
            schema = load_schema(schema_path)
        except Exception as exc:
            raise EventProcessingError(f"Failed to load sensor schema: {exc}") from exc

        self._table_schema: TableSchema = schema.tables["sensor_readings"]
        self._metrics_repo = metrics_aggregate_repo
        self._status_repo = status_repo
        # OrderedDict used as a bounded LRU cache: O(1) lookup + insertion-order
        # eviction.  Event IDs are only recorded *after* successful processing so
        # that a transient failure does not permanently drop the event on redelivery.
        self._seen_event_ids: OrderedDict[str, None] = OrderedDict()

    def handle(self, message: TransportMessage) -> None:
        """Process one message: parse → validate → clean → aggregate.

        Raises on any failure so the consumer can record and reject.
        Duplicate events (same event_id seen before) are silently skipped so
        that replay / redelivery cannot inflate aggregates.
        """
        # Step 1: structural parse
        raw_event = parse_event(message.payload)  # raises Malformed/EventValidation

        # Step 2: idempotency check — skip if already successfully processed
        if raw_event.event_id in self._seen_event_ids:
            _logger.debug("Duplicate event_id %s — skipped.", raw_event.event_id)
            return

        # Step 3: map to domain model
        reading = map_to_sensor_reading(raw_event)  # raises EventValidation on bad timestamp

        # Step 4: apply range validation and update aggregates
        try:
            self._process_reading(reading)
        except (MalformedEventError, EventValidationError):
            raise
        except Exception as exc:
            raise EventProcessingError(f"Unexpected error processing reading: {exc}") from exc

        # Record as seen only after successful processing so that redelivery after
        # a transient failure is retried rather than silently dropped.
        self._seen_event_ids[raw_event.event_id] = None
        if len(self._seen_event_ids) > _DEDUP_CACHE_MAX:
            self._seen_event_ids.popitem(last=False)  # evict oldest

    def _process_reading(self, reading: SensorReading, event_id: str | None = None) -> None:
        """Apply range cleaning and update all aggregate buckets."""
        raw_values = reading.sensor_values()

        for col_name, raw_value in raw_values.items():
            if raw_value is None:
                continue

            cleaned_value = self._nullify_if_out_of_range(col_name, raw_value)
            if cleaned_value is None:
                _logger.debug(
                    "Value %.3f for %s out of schema range; skipped for aggregation",
                    raw_value,
                    col_name,
                )
                continue

            for bucket in _BUCKETS:
                bucket_start = _floor_to_bucket(reading.timestamp, bucket)
                self._metrics_repo.upsert_aggregate(
                    station_id=reading.station_id,
                    device_id=reading.device_id,
                    metric_type=col_name,
                    bucket=bucket,
                    bucket_start=bucket_start,
                    value=cleaned_value,
                    timestamp=reading.timestamp,
                )

    def _nullify_if_out_of_range(self, col_name: str, value: float) -> float | None:
        """Return the value if within the schema-defined valid range, else None.

        Reuses ColumnSchema.valid_range from the loaded schema — the same
        source of truth used by the batch ingestion pipeline.
        """
        col_schema = self._table_schema.columns.get(col_name)
        if col_schema is None or col_schema.valid_range is None:
            return value
        min_val, max_val = col_schema.valid_range
        return value if min_val <= value <= max_val else None


def _floor_to_bucket(dt: datetime, bucket: str) -> datetime:
    """Floor a datetime to the start of the requested bucket."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    if bucket == "hour":
        return dt.replace(minute=0, second=0, microsecond=0)
    if bucket == "day":
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    raise ValueError(f"Unknown bucket type: {bucket!r}")
