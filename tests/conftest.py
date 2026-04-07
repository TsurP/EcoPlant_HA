"""Shared test fixtures."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from air_platform.config import AppSettings
from tests.constants import SCHEMA_PATH, TEST_STATION_ID

_DEVICES = [
    "5517e3df-a8a2-5eed-81cf-5f98ee0cbb15",
    "6628f4e0-b9b3-6ffe-92d0-6a09ff9dcc26",
    "7739e5f1-cac4-70ff-a3e1-7b1a000edd37",
]


def _create_test_sensor_db(db_path: Path) -> None:
    """Create a minimal SQLite sensor DB with realistic data for tests."""
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE station_metadata (
                station_id TEXT PRIMARY KEY,
                station_name TEXT NOT NULL,
                location TEXT NOT NULL,
                commissioned_date TEXT NOT NULL,
                num_compressors INTEGER NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE sensor_readings (
                timestamp TEXT NOT NULL,
                station_id TEXT NOT NULL,
                device_id TEXT NOT NULL,
                discharge_pressure REAL,
                air_flow_rate REAL,
                power_consumption REAL,
                motor_speed INTEGER,
                discharge_temp REAL
            )
        """)
        conn.execute(
            "INSERT INTO station_metadata VALUES (?, ?, ?, ?, ?)",
            (TEST_STATION_ID, "Test Station Alpha", "Building A", "2022-01-01", len(_DEVICES)),
        )

        rows = []
        base = "2024-02-01T{:02d}:{:02d}:00+00:00"
        for hour in range(12):
            for minute in range(0, 60, 5):
                # skip one interval on device 0 to create a gap
                if hour == 2 and minute == 15 and _DEVICES[0]:
                    continue
                ts = base.format(hour, minute)
                for i, device_id in enumerate(_DEVICES):
                    active = (hour % 3) != 0 or i == 1
                    pressure = 8.0 + i * 0.5 if active else 4.0
                    flow = 100.0 + i * 10 if active else 0.0
                    power = 50.0 + i * 5 if active else 0.0
                    rpm = 1500 + i * 100 if active else 0
                    temp = 45.0 + i * 2 if active else 20.0
                    # inject one flatline block on device 1 (constant for >30 min)
                    if device_id == _DEVICES[1] and 4 <= hour <= 5:
                        pressure = 9.0
                    # inject one None value
                    discharge_p: float | None = pressure
                    if hour == 6 and minute == 0 and i == 0:
                        discharge_p = None
                    rows.append(
                        (ts, TEST_STATION_ID, device_id, discharge_p, flow, power, rpm, temp)
                    )

        conn.executemany("INSERT INTO sensor_readings VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
        conn.commit()


@pytest.fixture(scope="session")
def test_sensor_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Session-scoped minimal sensor DB for integration and API tests."""
    db_path = tmp_path_factory.mktemp("db") / "sensor_data.db"
    _create_test_sensor_db(db_path)
    return db_path


@pytest.fixture
def test_station_id() -> str:
    return TEST_STATION_ID


@pytest.fixture
def app_settings(test_sensor_db: Path, tmp_path: Path) -> AppSettings:
    return AppSettings(
        sensor_db_path=test_sensor_db,
        sensor_schema_path=SCHEMA_PATH,
        metrics_db_path=tmp_path / "metrics.db",
        default_resample_frequency="30min",
        default_missing_strategy="fill",
        default_flatline_window_minutes=30,
        active_rpm_threshold=500,
        specific_power_flow_threshold=1.0,
    )
