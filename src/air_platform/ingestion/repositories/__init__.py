"""Repository adapters for raw data access."""

from air_platform.ingestion.repositories.base import SensorDataRepository
from air_platform.ingestion.repositories.sqlite import SQLiteSensorDataRepository

__all__ = ["SensorDataRepository", "SQLiteSensorDataRepository"]
