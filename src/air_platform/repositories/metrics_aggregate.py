"""In-memory repository for incrementally aggregated stream metrics."""

from __future__ import annotations

import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

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
    """

    def __init__(self) -> None:
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
    ) -> None:
        """Insert or update the running aggregate for a single data point."""
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
        """Return aggregates matching the given filters, sorted for consistency."""
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
                results.append(agg)

        results.sort(key=lambda a: (a.device_id, a.metric_type, a.bucket, a.bucket_start))
        return results
