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
