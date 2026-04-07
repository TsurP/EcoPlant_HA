# Air Platform

Reusable compressed-air sensor ingestion library with a thin FastAPI metrics service on top.

The repository is intentionally library-first:

- `air_platform.ingestion` handles raw data access, schema validation, cleaning, resampling, and quality reporting.
- `air_platform.metrics` computes typed operational metrics from processed datasets.
- `air_platform.service` exposes the workflow through FastAPI without embedding business logic in routes.
- `air_platform.storage` persists computed metrics behind a repository abstraction.

## Project overview

The assignment data lives in SQLite and is validated against `data/sensor_schema.json`. A processing request does the following:

1. Load station readings through a repository interface.
2. Validate required columns, timestamps, numeric coercion, and schema ranges.
3. Nullify impossible values and report quality issues.
4. Apply a configurable missing-data strategy.
5. Resample per station and device.
6. Compute operational metrics.
7. Persist metric results in SQLite with an upsert strategy.

The service returns a structured processing summary and exposes stored metrics through a read endpoint.

## Architecture summary

### 1. Ingestion library

- `src/air_platform/ingestion/repositories/base.py`: raw data repository contract.
- `src/air_platform/ingestion/repositories/sqlite.py`: SQLite implementation for station data.
- `src/air_platform/ingestion/schema_loader.py`: JSON schema parsing.
- `src/air_platform/ingestion/validators.py`: required-column, type, and range validation.
- `src/air_platform/ingestion/quality.py`: missing percentages, timestamp gaps, and flatline detection.
- `src/air_platform/ingestion/cleaners.py`: missing-data handling strategies.
- `src/air_platform/ingestion/resampling.py`: grouped time-series resampling.
- `src/air_platform/ingestion/pipeline.py`: orchestration returning a `ProcessedDataset`.

### 2. Metrics engine

- `src/air_platform/metrics/engine.py`: pure metric computation from `ProcessedDataset`.
- `src/air_platform/metrics/models.py`: typed metric config, results, and query filters.
- `src/air_platform/metrics/definitions.py`: metric metadata and units.

### 3. API and storage

- `src/air_platform/storage/base.py`: metric storage contract.
- `src/air_platform/storage/sqlite.py`: SQLite metric store with upsert semantics.
- `src/air_platform/service/orchestrator.py`: service-layer orchestration.
- `src/air_platform/service/routes.py`: thin FastAPI routes.
- `src/air_platform/service/schemas.py`: Pydantic v2 request and response models.

## Repository layout

```text
.
├── data/
│   ├── sensor_data.db
│   └── sensor_schema.json
├── src/air_platform/
├── tests/
│   ├── api/
│   ├── integration/
│   └── unit/
├── .github/workflows/ci.yml
├── Makefile
├── pyproject.toml
└── uv.lock
```

## Setup

Target runtime: Python 3.12 with `uv`.

```bash
make install
```

Equivalent direct command:

```bash
uv sync --dev
```

Optional environment overrides:

- `AIR_PLATFORM_SENSOR_DB_PATH`
- `AIR_PLATFORM_SENSOR_SCHEMA_PATH`
- `AIR_PLATFORM_METRICS_DB_PATH`
- `AIR_PLATFORM_DEFAULT_RESAMPLE_FREQUENCY`
- `AIR_PLATFORM_DEFAULT_MISSING_STRATEGY`
- `AIR_PLATFORM_DEFAULT_FLATLINE_WINDOW_MINUTES`
- `AIR_PLATFORM_ACTIVE_RPM_THRESHOLD`
- `AIR_PLATFORM_SPECIFIC_POWER_FLOW_THRESHOLD`

By default the API reads from `data/sensor_data.db` and `data/sensor_schema.json`, and creates `data/metrics.db` on first write.

## Common commands

```bash
make lint
make format
make typecheck
make test
make run
```

Current local verification:

- `uv run ruff check .`
- `uv run mypy src tests`
- `uv run pytest`

## Running the API

```bash
make run
```

This starts:

```text
uvicorn air_platform.service.app:app --reload
```

Default base URL:

```text
http://127.0.0.1:8000
```

## Endpoint summary

### `GET /health`

Simple readiness check.

Response:

```json
{"status": "ok"}
```

### `POST /stations/{station_id}/process`

Triggers ingestion, cleaning, resampling, metric computation, and persistence.

Example:

```bash
curl -X POST http://127.0.0.1:8000/stations/d43f07f0-0170-5663-a459-04597edb38b6/process \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2024-02-01T00:00:00+00:00",
    "end_time": "2024-02-01T06:00:00+00:00",
    "resample_frequency": "30min",
    "missing_strategy": "fill",
    "flatline_window_minutes": 30,
    "active_rpm_threshold": 500,
    "specific_power_flow_threshold": 1.0
  }'
```

Supported request fields:

- `start_time`
- `end_time`
- `resample_frequency`
- `missing_strategy`: `drop`, `fill`, `interpolate`
- `flatline_window_minutes`
- `active_rpm_threshold`
- `specific_power_flow_threshold`

### `GET /metrics`

Reads persisted metrics with optional filters:

- `station_id`
- `device_id`
- `start_time`
- `end_time`
- `metric_name`

Example:

```bash
curl "http://127.0.0.1:8000/metrics?station_id=d43f07f0-0170-5663-a459-04597edb38b6&metric_name=average_pressure_bar"
```

## Processing behavior

### Validation

Hard failures:

- missing required columns
- unreadable schema
- no station data found
- all timestamps unreadable
- no usable rows after cleaning or resampling

Quality findings that are reported instead of failing:

- malformed numeric values coerced to null
- out-of-range values
- timestamp gaps
- flatline periods
- per-column missing percentages

### Cleaning strategy

Chosen behavior:

- numeric columns are coerced with `pandas.to_numeric(errors="coerce")`
- out-of-range values are converted to null and counted in the quality report
- missing handling is explicit and configurable:
  - `drop`: remove rows with missing sensor values
  - `fill`: forward-fill then backfill per device
  - `interpolate`: time-based interpolation per device

Default service setting: `fill`

### Resampling

Resampling is performed per `station_id` and `device_id` using mean aggregation for:

- `discharge_pressure`
- `air_flow_rate`
- `power_consumption`
- `motor_speed`
- `discharge_temp`

This keeps timestamp alignment explicit and easy to explain for interview discussion.

### Data quality report

Each processing run returns:

- rows read
- rows after cleaning
- per-column missing percentages
- out-of-range counts
- malformed value counts
- timestamp gap details
- flatline period details
- warning summary strings

Flatline detection uses the greater of:

- the request-level flatline window
- sensor-specific thresholds defined in `sensor_schema.json`

## Metric definitions

The engine computes metrics per device:

- `active_duration_hours`
  Active time where `motor_speed > active_rpm_threshold`.
- `active_ratio_pct`
  Active sample ratio over the processed window.
- `average_pressure_bar`
  Mean `discharge_pressure` after cleaning and resampling.
- `peak_pressure_bar`
  Max `discharge_pressure` after cleaning and resampling.
- `mean_specific_power_kw_per_m3h`
  Mean of `power_consumption / air_flow_rate` for rows where flow is above `specific_power_flow_threshold`.
- `cycle_count`
  Count of inactive-to-active transitions within the observed window.
- `total_flow_volume_m3`
  Sum of `air_flow_rate * interval_hours` across the resampled series.

Metric results store:

- `station_id`
- `device_id`
- `metric_name`
- `metric_value`
- `unit`
- `window_start`
- `window_end`
- `computed_at`
- `resample_frequency`
- `missing_strategy`

## Tests

The test suite is split by layer:

- `tests/unit`
  Pure validation, cleaning, quality, resampling, and metric logic.
- `tests/integration`
  SQLite repository behavior, pipeline execution, and metric persistence.
- `tests/api`
  FastAPI endpoint behavior and filter handling.

Covered cases include:

- missing required columns
- malformed and out-of-range values
- timestamp gap detection
- flatline detection
- missing-data strategies
- zero-flow specific power behavior
- cycle-count edge cases
- invalid station handling
- API retrieval filters

## Design decisions and tradeoffs

- Library-first over framework-first: the ingestion and metric logic can be reused by batch jobs, notebooks, or workers without importing FastAPI.
- SQLite behind interfaces: raw input storage and metric output storage are both abstracted, so swapping to Postgres or BigQuery is a repository change rather than a pipeline rewrite.
- Simple deterministic cleaning: `drop`, `fill`, and `interpolate` were chosen because they are explainable and easy to test.
- Typed outputs over loose DataFrames: the ingestion pipeline returns a structured `ProcessedDataset` with cleaning and quality metadata instead of only returning a bare table.
- Practical idempotency: metrics use a composite primary key and SQLite upsert so reprocessing the same window/config overwrites prior values cleanly.

## CI/CD

### CI

The included GitHub Actions workflow runs:

1. `uv sync --frozen --dev`
2. `uv run ruff check .`
3. `uv run ruff format --check .`
4. `uv run mypy src tests`
5. `uv run pytest`

### CD

A production-minded deployment path would be:

1. Build a Docker image for the FastAPI service.
2. Push the image to a registry.
3. Deploy to the target platform.
4. Run smoke checks against `/health`.
5. Apply storage migrations if the metric schema evolves.

The repository stops at CI because deployment target details were not part of the assignment.
