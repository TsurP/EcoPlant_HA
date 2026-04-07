from __future__ import annotations

import pandas as pd
import pytest

from air_platform.errors import ValidationError
from air_platform.ingestion.schema_loader import load_schema
from air_platform.ingestion.validators import normalize_sensor_dataframe, validate_required_columns
from tests.constants import SCHEMA_PATH


def test_validate_required_columns_raises_when_required_field_missing() -> None:
    schema = load_schema(SCHEMA_PATH)
    dataframe = pd.DataFrame({"station_id": ["station-1"], "device_id": ["device-1"]})

    with pytest.raises(ValidationError, match="Missing required columns"):
        validate_required_columns(dataframe, schema.tables["sensor_readings"])


def test_normalize_sensor_dataframe_counts_malformed_and_out_of_range_values() -> None:
    schema = load_schema(SCHEMA_PATH)
    dataframe = pd.DataFrame(
        {
            "timestamp": ["2024-02-01T00:00:00+00:00", "2024-02-01T00:01:00+00:00"],
            "station_id": ["station-1", "station-1"],
            "device_id": ["device-1", "device-1"],
            "discharge_pressure": ["bad", 20.0],
            "air_flow_rate": [100.0, 900.0],
            "power_consumption": [10.0, 20.0],
            "motor_speed": [900, 1000],
            "discharge_temp": [40.0, 41.0],
        }
    )

    result = normalize_sensor_dataframe(dataframe, schema.tables["sensor_readings"])

    assert result.malformed_value_counts["discharge_pressure"] == 1
    assert result.out_of_range_counts["discharge_pressure"] == 1
    assert result.out_of_range_counts["air_flow_rate"] == 1


def test_normalize_sensor_dataframe_fails_when_all_timestamps_unreadable() -> None:
    schema = load_schema(SCHEMA_PATH)
    dataframe = pd.DataFrame(
        {
            "timestamp": ["not-a-timestamp"],
            "station_id": ["station-1"],
            "device_id": ["device-1"],
        }
    )

    with pytest.raises(ValidationError, match="unreadable"):
        normalize_sensor_dataframe(dataframe, schema.tables["sensor_readings"])


def test_normalize_sensor_dataframe_does_not_count_already_null_as_malformed() -> None:
    """Pre-existing nulls must not inflate the malformed count."""
    schema = load_schema(SCHEMA_PATH)
    dataframe = pd.DataFrame(
        {
            "timestamp": ["2024-02-01T00:00:00+00:00"],
            "station_id": ["station-1"],
            "device_id": ["device-1"],
            "discharge_pressure": [None],  # already null, not malformed
            "air_flow_rate": [100.0],
            "power_consumption": [10.0],
            "motor_speed": [900],
            "discharge_temp": [40.0],
        }
    )

    result = normalize_sensor_dataframe(dataframe, schema.tables["sensor_readings"])

    assert result.malformed_value_counts["discharge_pressure"] == 0


def test_normalize_sensor_dataframe_out_of_range_at_boundary_is_within_range() -> None:
    """Values exactly at the schema boundary should not be reported as out-of-range."""
    schema = load_schema(SCHEMA_PATH)
    sensor_schema = schema.tables["sensor_readings"]
    pressure_range = sensor_schema.columns["discharge_pressure"].valid_range
    assert pressure_range is not None
    min_val, max_val = pressure_range

    dataframe = pd.DataFrame(
        {
            "timestamp": ["2024-02-01T00:00:00+00:00", "2024-02-01T00:01:00+00:00"],
            "station_id": ["station-1", "station-1"],
            "device_id": ["device-1", "device-1"],
            "discharge_pressure": [min_val, max_val],
            "air_flow_rate": [100.0, 100.0],
            "power_consumption": [10.0, 10.0],
            "motor_speed": [900, 900],
            "discharge_temp": [40.0, 40.0],
        }
    )

    result = normalize_sensor_dataframe(dataframe, sensor_schema)

    assert result.out_of_range_counts["discharge_pressure"] == 0
