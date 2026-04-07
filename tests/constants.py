"""Shared constants for the test suite."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
SENSOR_DB_PATH = DATA_DIR / "sensor_data.db"
SCHEMA_PATH = DATA_DIR / "sensor_schema.json"
TEST_STATION_ID = "d43f07f0-0170-5663-a459-04597edb38b6"
