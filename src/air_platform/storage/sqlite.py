"""SQLite-backed metric results repository."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

from air_platform.errors import StorageError
from air_platform.metrics.models import MetricQuery, MetricResult


def _to_utc_naive_iso(dt: datetime) -> str:
    """Normalise *dt* to UTC and strip tzinfo before storing / querying.

    SQLite has no native datetime type and compares TEXT columns
    lexicographically.  All timestamps must use the same representation so
    that range queries and the upsert primary key both work correctly regardless
    of the timezone offset on the incoming ``datetime`` object.
    """
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.isoformat()


class SQLiteMetricResultRepository:
    """Persist computed metrics in SQLite."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def save_metric_results(self, results: list[MetricResult]) -> None:
        if not results:
            return

        statement = """
            INSERT INTO metric_results (
                station_id,
                device_id,
                metric_name,
                metric_value,
                unit,
                window_start,
                window_end,
                computed_at,
                resample_frequency,
                missing_strategy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (
                station_id,
                device_id,
                metric_name,
                window_start,
                window_end,
                resample_frequency,
                missing_strategy
            ) DO UPDATE SET
                metric_value = excluded.metric_value,
                unit = excluded.unit,
                computed_at = excluded.computed_at
        """
        payload = [
            (
                result.station_id,
                result.device_id,
                result.metric_name,
                result.metric_value,
                result.unit,
                _to_utc_naive_iso(result.window_start),
                _to_utc_naive_iso(result.window_end),
                _to_utc_naive_iso(result.computed_at),
                result.resample_frequency,
                result.missing_strategy,
            )
            for result in results
        ]

        try:
            with sqlite3.connect(self.db_path) as connection:
                connection.executemany(statement, payload)
                connection.commit()
        except sqlite3.Error as exc:
            raise StorageError("Failed to save metric results") from exc

    def get_metric_results(self, query: MetricQuery) -> list[MetricResult]:
        statement = """
            SELECT
                station_id,
                device_id,
                metric_name,
                metric_value,
                unit,
                window_start,
                window_end,
                computed_at,
                resample_frequency,
                missing_strategy
            FROM metric_results
            WHERE 1 = 1
        """
        parameters: list[object] = []

        if query.station_id is not None:
            statement += " AND station_id = ?"
            parameters.append(query.station_id)
        if query.device_id is not None:
            statement += " AND device_id = ?"
            parameters.append(query.device_id)
        if query.metric_name is not None:
            statement += " AND metric_name = ?"
            parameters.append(query.metric_name)
        if query.start_time is not None:
            statement += " AND window_end >= ?"
            parameters.append(_to_utc_naive_iso(query.start_time))
        if query.end_time is not None:
            statement += " AND window_start <= ?"
            parameters.append(_to_utc_naive_iso(query.end_time))

        statement += " ORDER BY station_id, device_id, metric_name, window_start"

        try:
            with sqlite3.connect(self.db_path) as connection:
                connection.row_factory = sqlite3.Row
                rows = connection.execute(statement, parameters).fetchall()
        except sqlite3.Error as exc:
            raise StorageError("Failed to retrieve metric results") from exc

        return [
            MetricResult(
                station_id=str(row["station_id"]),
                device_id=str(row["device_id"]),
                metric_name=str(row["metric_name"]),
                metric_value=float(row["metric_value"]),
                unit=str(row["unit"]),
                window_start=datetime.fromisoformat(str(row["window_start"])),
                window_end=datetime.fromisoformat(str(row["window_end"])),
                computed_at=datetime.fromisoformat(str(row["computed_at"])),
                resample_frequency=str(row["resample_frequency"]),
                missing_strategy=str(row["missing_strategy"]),
            )
            for row in rows
        ]

    def _ensure_schema(self) -> None:
        statement = """
            CREATE TABLE IF NOT EXISTS metric_results (
                station_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                metric_name TEXT NOT NULL,
                metric_value REAL NOT NULL,
                unit TEXT NOT NULL,
                window_start TEXT NOT NULL,
                window_end TEXT NOT NULL,
                computed_at TEXT NOT NULL,
                resample_frequency TEXT NOT NULL,
                missing_strategy TEXT NOT NULL,
                PRIMARY KEY (
                    station_id,
                    device_id,
                    metric_name,
                    window_start,
                    window_end,
                    resample_frequency,
                    missing_strategy
                )
            )
        """
        index_statement = """
            CREATE INDEX IF NOT EXISTS idx_metric_results_filters
            ON metric_results (station_id, device_id, metric_name, window_start, window_end)
        """
        try:
            with sqlite3.connect(self.db_path) as connection:
                connection.execute(statement)
                connection.execute(index_statement)
                connection.commit()
        except sqlite3.Error as exc:
            raise StorageError("Failed to initialize metrics storage") from exc
