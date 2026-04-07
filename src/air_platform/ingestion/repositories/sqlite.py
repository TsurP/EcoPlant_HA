"""SQLite implementation of the raw sensor repository."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

from air_platform.errors import StorageError
from air_platform.ingestion.models import StationMetadata


class SQLiteSensorDataRepository:
    """Load raw readings and station metadata from SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def fetch_sensor_readings(
        self,
        station_id: str,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> pd.DataFrame:
        query = """
            SELECT
                timestamp,
                station_id,
                device_id,
                discharge_pressure,
                air_flow_rate,
                power_consumption,
                motor_speed,
                discharge_temp
            FROM sensor_readings
            WHERE station_id = ?
        """
        parameters: list[str] = [station_id]
        if start_time is not None:
            query += " AND timestamp >= ?"
            parameters.append(start_time.isoformat())
        if end_time is not None:
            query += " AND timestamp <= ?"
            parameters.append(end_time.isoformat())
        query += " ORDER BY device_id, timestamp"

        try:
            with sqlite3.connect(self.db_path) as connection:
                return pd.read_sql_query(query, connection, params=tuple(parameters))
        except sqlite3.Error as exc:
            raise StorageError(f"Failed to fetch sensor readings for station {station_id}") from exc

    def fetch_station_metadata(self, station_id: str) -> StationMetadata | None:
        query = """
            SELECT
                station_id,
                station_name,
                location,
                commissioned_date,
                num_compressors
            FROM station_metadata
            WHERE station_id = ?
        """
        try:
            with sqlite3.connect(self.db_path) as connection:
                connection.row_factory = sqlite3.Row
                row = connection.execute(query, (station_id,)).fetchone()
        except sqlite3.Error as exc:
            raise StorageError(
                f"Failed to fetch station metadata for station {station_id}"
            ) from exc

        if row is None:
            return None

        return StationMetadata(
            station_id=str(row["station_id"]),
            station_name=str(row["station_name"]),
            location=str(row["location"]),
            commissioned_date=str(row["commissioned_date"]),
            num_compressors=int(row["num_compressors"]),
        )
