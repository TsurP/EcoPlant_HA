"""In-memory repository for incrementally aggregated stream metrics."""

from __future__ import annotations

import copy
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AggregateKey:
    """Composite key for a single aggregate bucket."""

    station_id: str
    device_id: str
    metric_type: str
    bucket: str  # "hour" or "day"
    bucket_start: datetime


@dataclass
class MetricAggregate:
    """Running aggregate for one metric/bucket combination."""

    station_id: str
    device_id: str
    metric_type: str
    bucket: str
    bucket_start: datetime
    count: int = 0
    total: float = 0.0
    min_value: float | None = None
    max_value: float | None = None
    avg: float = 0.0
    latest_timestamp: datetime | None = None


# ---------------------------------------------------------------------------
# Protocol (interface)
# ---------------------------------------------------------------------------


class MetricsAggregateRepository(Protocol):
    """Interface for storing and querying incremental aggregates."""

    def upsert_aggregate(
        self,
        station_id: str,
        device_id: str,
        metric_type: str,
        bucket: str,
        bucket_start: datetime,
        value: float,
        timestamp: datetime,
        event_id: str | None = None,
    ) -> None: ...

    def query(
        self,
        station_id: str,
        device_id: str | None = None,
        metric_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        bucket: str | None = None,
    ) -> list[MetricAggregate]: ...


# ---------------------------------------------------------------------------
# In-memory implementation
# ---------------------------------------------------------------------------


class InMemoryMetricsAggregateRepository:
    """Thread-safe in-memory aggregate store.

    Keyed by ``(station_id, device_id, metric_type, bucket, bucket_start)``.
    Aggregates are updated incrementally as new readings arrive.

    ``max_buckets`` caps the total number of distinct bucket entries kept in
    memory.  When the cap is exceeded the oldest buckets (by ``bucket_start``)
    are evicted first, preventing unbounded growth in long-running consumers.
    """

    _DEFAULT_MAX_BUCKETS: int = 10_000

    def __init__(self, max_buckets: int = _DEFAULT_MAX_BUCKETS) -> None:
        if max_buckets < 1:
            raise ValueError(f"max_buckets must be >= 1, got {max_buckets}")
        self._max_buckets = max_buckets
        self._data: dict[AggregateKey, MetricAggregate] = {}
        self._lock = threading.Lock()

    def upsert_aggregate(
        self,
        station_id: str,
        device_id: str,
        metric_type: str,
        bucket: str,
        bucket_start: datetime,
        value: float,
        timestamp: datetime,
        event_id: str | None = None,
    ) -> None:
        """Insert or update the running aggregate for a single data point.

        Naive *timestamp* values are treated as UTC to prevent
        ``TypeError: can't compare offset-naive and offset-aware datetimes``
        when the running ``latest_timestamp`` was previously set from an
        aware datetime.

        *event_id* is accepted for interface compatibility but deduplication
        is handled at the caller (``EventHandler``) level, not here.
        """
        if timestamp.tzinfo is None:
            timestamp = timestamp.replace(tzinfo=UTC)
        key = AggregateKey(station_id, device_id, metric_type, bucket, bucket_start)
        with self._lock:
            existing = self._data.get(key)
            if existing is None:
                self._data[key] = MetricAggregate(
                    station_id=station_id,
                    device_id=device_id,
                    metric_type=metric_type,
                    bucket=bucket,
                    bucket_start=bucket_start,
                    count=1,
                    total=value,
                    min_value=value,
                    max_value=value,
                    avg=value,
                    latest_timestamp=timestamp,
                )
                # Evict oldest bucket when cap is exceeded.
                if len(self._data) > self._max_buckets:
                    oldest = min(self._data, key=lambda k: k.bucket_start)
                    evicted = self._data.pop(oldest)
                    _logger.warning(
                        "Aggregate bucket evicted (max_buckets=%d): "
                        "station=%s device=%s metric=%s bucket=%s start=%s",
                        self._max_buckets,
                        evicted.station_id,
                        evicted.device_id,
                        evicted.metric_type,
                        evicted.bucket,
                        evicted.bucket_start,
                    )
            else:
                new_count = existing.count + 1
                new_total = existing.total + value
                existing.count = new_count
                existing.total = new_total
                existing.avg = new_total / new_count
                existing.min_value = (
                    min(existing.min_value, value) if existing.min_value is not None else value
                )
                existing.max_value = (
                    max(existing.max_value, value) if existing.max_value is not None else value
                )
                existing.latest_timestamp = (
                    max(existing.latest_timestamp, timestamp)
                    if existing.latest_timestamp is not None
                    else timestamp
                )

    def query(
        self,
        station_id: str,
        device_id: str | None = None,
        metric_type: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        bucket: str | None = None,
    ) -> list[MetricAggregate]:
        """Return aggregates matching the given filters, sorted for consistency.

        Naive datetimes in *start_time* / *end_time* are treated as UTC so that
        callers passing plain ``datetime(2024, 1, 1)`` never trigger a
        ``TypeError: can't compare offset-naive and offset-aware datetimes``.
        """
        start_time = _to_utc(start_time)
        end_time = _to_utc(end_time)

        with self._lock:
            results: list[MetricAggregate] = []
            for key, agg in self._data.items():
                if key.station_id != station_id:
                    continue
                if device_id is not None and key.device_id != device_id:
                    continue
                if metric_type is not None and key.metric_type != metric_type:
                    continue
                if bucket is not None and key.bucket != bucket:
                    continue
                if start_time is not None and key.bucket_start < start_time:
                    continue
                if end_time is not None and key.bucket_start >= end_time:
                    continue
                # Return a shallow copy so callers cannot mutate stored state.
                results.append(copy.copy(agg))

        results.sort(key=lambda a: (a.device_id, a.metric_type, a.bucket, a.bucket_start))
        return results


def _to_utc(dt: datetime | None) -> datetime | None:
    """Attach UTC timezone to a naive datetime; leave aware datetimes unchanged."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt
