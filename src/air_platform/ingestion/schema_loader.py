"""Load the JSON schema used by the ingestion pipeline."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from air_platform.errors import SchemaLoadError
from air_platform.ingestion.models import ColumnSchema, SensorSchema, SensorTypeSchema, TableSchema


def load_schema(schema_path: str | Path) -> SensorSchema:
    """Load and parse the sensor schema document."""

    try:
        with Path(schema_path).open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise SchemaLoadError(f"Unable to load schema from {schema_path}") from exc

    try:
        tables = {
            table_name: _parse_table_schema(table_name, table_payload)
            for table_name, table_payload in payload["tables"].items()
        }
        sensor_types = {
            sensor_name: _parse_sensor_type(sensor_name, sensor_payload)
            for sensor_name, sensor_payload in payload.get("sensor_types", {}).items()
        }
        return SensorSchema(
            version=str(payload["version"]),
            tables=tables,
            sensor_types=sensor_types,
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise SchemaLoadError("Schema file is missing required fields") from exc


def _parse_table_schema(name: str, payload: dict[str, Any]) -> TableSchema:
    columns = {
        column_name: _parse_column_schema(column_name, column_payload)
        for column_name, column_payload in payload["columns"].items()
    }
    return TableSchema(name=name, columns=columns)


def _parse_column_schema(name: str, payload: dict[str, Any]) -> ColumnSchema:
    valid_range = payload.get("valid_range")
    parsed_range: tuple[float, float] | None = None
    if isinstance(valid_range, dict):
        parsed_range = (float(valid_range["min"]), float(valid_range["max"]))

    return ColumnSchema(
        name=name,
        data_type=str(payload["type"]),
        required=bool(payload.get("required", False)),
        valid_range=parsed_range,
        unit=payload.get("unit"),
        description=str(payload.get("description", "")),
    )


def _parse_sensor_type(name: str, payload: dict[str, Any]) -> SensorTypeSchema:
    operating_range = payload.get("typical_operating_range")
    parsed_range: tuple[float, float] | None = None
    if isinstance(operating_range, dict):
        parsed_range = (float(operating_range["min"]), float(operating_range["max"]))

    flatline_threshold = payload.get("flatline_threshold_minutes")
    return SensorTypeSchema(
        name=name,
        flatline_threshold_minutes=(
            int(flatline_threshold) if flatline_threshold is not None else None
        ),
        typical_operating_range=parsed_range,
    )
