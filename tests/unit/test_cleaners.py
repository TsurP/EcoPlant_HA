from __future__ import annotations

import pandas as pd

from air_platform.ingestion.cleaners import apply_missing_strategy, nullify_out_of_range_values
from air_platform.ingestion.models import ColumnSchema, MissingStrategy, TableSchema


def test_fill_strategy_forward_fills_trailing_nulls() -> None:
    """ffill propagates the last known value forward; trailing nulls are filled."""
    dataframe = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:01:00+00:00",
                    "2024-02-01T00:02:00+00:00",
                ],
                utc=True,
            ),
            "station_id": ["station-1"] * 3,
            "device_id": ["device-1"] * 3,
            "discharge_pressure": [None, 7.0, None],
        }
    )

    cleaned = apply_missing_strategy(dataframe, ["discharge_pressure"], MissingStrategy.FILL)

    # Row 0: no prior value → stays NaN (no back-fill to avoid leaking future data).
    # Row 2: forward-filled from row 1.
    import math

    assert math.isnan(cleaned["discharge_pressure"].iloc[0])
    assert cleaned["discharge_pressure"].iloc[1] == 7.0
    assert cleaned["discharge_pressure"].iloc[2] == 7.0


def test_fill_strategy_does_not_backfill_leading_nulls() -> None:
    """A leading null must not be filled backward — that would use a future value."""
    dataframe = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:01:00+00:00",
                ],
                utc=True,
            ),
            "station_id": ["station-1"] * 2,
            "device_id": ["device-1"] * 2,
            "discharge_pressure": [None, 9.0],
        }
    )

    cleaned = apply_missing_strategy(dataframe, ["discharge_pressure"], MissingStrategy.FILL)

    import math

    assert math.isnan(cleaned["discharge_pressure"].iloc[0])
    assert cleaned["discharge_pressure"].iloc[1] == 9.0


def test_interpolate_strategy_interpolates_over_time() -> None:
    dataframe = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:10:00+00:00",
                    "2024-02-01T00:20:00+00:00",
                ],
                utc=True,
            ),
            "station_id": ["station-1"] * 3,
            "device_id": ["device-1"] * 3,
            "discharge_pressure": [0.0, None, 20.0],
        }
    )

    cleaned = apply_missing_strategy(
        dataframe,
        ["discharge_pressure"],
        MissingStrategy.INTERPOLATE,
    )

    assert cleaned["discharge_pressure"].tolist() == [0.0, 10.0, 20.0]


def test_drop_strategy_removes_rows_with_missing_sensor_values() -> None:
    dataframe = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2024-02-01T00:00:00+00:00",
                    "2024-02-01T00:01:00+00:00",
                ],
                utc=True,
            ),
            "station_id": ["station-1", "station-1"],
            "device_id": ["device-1", "device-1"],
            "discharge_pressure": [7.0, None],
        }
    )

    cleaned = apply_missing_strategy(dataframe, ["discharge_pressure"], MissingStrategy.DROP)

    assert len(cleaned) == 1


def _make_table_schema(col: str, min_val: float, max_val: float) -> TableSchema:
    return TableSchema(
        name="test",
        columns={
            col: ColumnSchema(
                name=col,
                data_type="float",
                required=True,
                valid_range=(min_val, max_val),
            )
        },
    )


def test_nullify_out_of_range_replaces_out_of_range_values() -> None:
    schema = _make_table_schema("discharge_pressure", 0.0, 15.0)
    dataframe = pd.DataFrame({"discharge_pressure": [5.0, 20.0, -1.0, 10.0]})

    cleaned, count = nullify_out_of_range_values(dataframe, schema)

    assert count == 2
    assert cleaned["discharge_pressure"].isna().sum() == 2
    assert cleaned["discharge_pressure"].iloc[0] == 5.0
    assert cleaned["discharge_pressure"].iloc[3] == 10.0


def test_nullify_out_of_range_keeps_boundary_values() -> None:
    """Values exactly at the valid range boundaries must not be nullified."""
    schema = _make_table_schema("discharge_pressure", 0.0, 15.0)
    dataframe = pd.DataFrame({"discharge_pressure": [0.0, 15.0]})

    cleaned, count = nullify_out_of_range_values(dataframe, schema)

    assert count == 0
    assert cleaned["discharge_pressure"].isna().sum() == 0


def test_nullify_out_of_range_leaves_existing_nulls_unchanged() -> None:
    schema = _make_table_schema("discharge_pressure", 0.0, 15.0)
    dataframe = pd.DataFrame({"discharge_pressure": [None, 5.0]})

    cleaned, count = nullify_out_of_range_values(dataframe, schema)

    assert count == 0
    assert cleaned["discharge_pressure"].isna().sum() == 1


def test_fill_strategy_handles_all_null_column_gracefully() -> None:
    """When a column is entirely null, fill leaves it null (no crash)."""
    dataframe = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                ["2024-02-01T00:00:00+00:00", "2024-02-01T00:01:00+00:00"],
                utc=True,
            ),
            "station_id": ["s1", "s1"],
            "device_id": ["d1", "d1"],
            "discharge_pressure": [None, None],
        }
    )

    cleaned = apply_missing_strategy(dataframe, ["discharge_pressure"], MissingStrategy.FILL)

    assert len(cleaned) == 2
    assert cleaned["discharge_pressure"].isna().all()
