"""Metric storage abstractions and adapters."""

from air_platform.storage.base import MetricResultRepository
from air_platform.storage.sqlite import SQLiteMetricResultRepository

__all__ = ["MetricResultRepository", "SQLiteMetricResultRepository"]
