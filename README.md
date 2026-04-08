# Air Platform

Reusable compressed-air sensor ingestion library with a thin FastAPI metrics service, plus an **LLM integration layer** for plain-English summaries, natural-language metric queries, and AI-generated data quality reports.

This repository is intentionally **library-first**. Core ingestion, validation, cleaning, resampling, metric computation, and data quality detection live in reusable Python modules. FastAPI is a thin orchestration layer over those deterministic services. The LLM layer sits above the deterministic system and is never allowed to perform metric computation.

---

## What this project does

Given compressed-air sensor data stored in SQLite, the project can:

- validate and clean station data against a JSON schema
- detect data quality issues such as missing values, flatlines, and timestamp gaps
- resample and normalize time-series data per station and device
- compute operational metrics deterministically
- persist computed metrics for later retrieval
- generate natural-language summaries and reports using OpenAI
- translate plain-English metric questions into validated structured queries

---

## Why this design

The system is split into five layers:

- **`air_platform.ingestion`** – raw data access, schema validation, cleaning, resampling, and data quality reporting
- **`air_platform.metrics`** – pure typed metric computation from processed datasets
- **`air_platform.service`** – FastAPI orchestration and request/response handling without business logic in routes
- **`air_platform.storage`** – persistence of computed metrics behind a repository abstraction
- **`air_platform.llm`** – provider abstraction, OpenAI implementation, prompt templates, and application use cases for LLM-powered features

This makes the core logic reusable from APIs, batch jobs, notebooks, or future workers. It also keeps the LLM in the right place: **language generation and structured extraction only**. All numeric computation remains deterministic and owned by the service layer.

---

## 5-minute demo flow

A reviewer can verify the project with the following flow:

1. Start the API
2. Check `GET /health`
3. Run `POST /stations/{station_id}/process`
4. Fetch stored metrics with `GET /metrics`
5. If `AIR_PLATFORM_OPENAI_API_KEY` is set:
   - call `POST /stations/{station_id}/summary`
   - call `POST /llm/query`
   - call `POST /stations/{station_id}/quality-report`

This exercises both the deterministic pipeline and the LLM layer.

---

## Quickstart

### Requirements

- Python 3.12
- [`uv`](https://docs.astral.sh/uv/)

### Install dependencies

```bash
make install
```

Equivalent direct command:

```bash
uv sync --dev
```

### Run checks

```bash
make lint
make typecheck
make test
```

### Start the API

Without LLM features:

```bash
make run
```

With LLM features enabled:

```bash
AIR_PLATFORM_OPENAI_API_KEY=sk-... make run
```

The service starts with:

```bash
uvicorn air_platform.service.app:app --reload
```

> **Challenge 3 — event-driven stream:**  The in-process queue used by the
> background consumer is a Python `queue.Queue`.  Because it is an in-process
> data structure, the producer and consumer **must share the same queue
> instance in the same Python process**.  `make run` / `uvicorn` alone does
> **not** wire the producer; use `run_with_producer.py` instead:
>
> ```bash
> uv run python run_with_producer.py
> ```
>
> This script creates the shared queue, starts the producer in a daemon
> thread, and passes the queue into `create_app()` so the API consumer reads
> from the same source.  The server still listens on `http://127.0.0.1:8000`.

Default base URL:

```text
http://127.0.0.1:8000
```

### Verify it is running

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status": "ok"}
```

---

## Environment setup

A typical local setup can be done with environment variables or a local `.env` file.

Example:

```bash
export AIR_PLATFORM_OPENAI_API_KEY=sk-...
export AIR_PLATFORM_OPENAI_MODEL=gpt-4o-mini
export AIR_PLATFORM_OPENAI_TIMEOUT_SECONDS=30
export AIR_PLATFORM_OPENAI_MAX_RETRIES=3
```

---

## Project overview

The assignment data lives in SQLite and is validated against `data/sensor_schema.json`.

A processing request performs the following steps:

1. Load station readings through a repository interface
2. Validate required columns, timestamps, numeric coercion, and schema ranges
3. Nullify impossible values and record quality issues
4. Apply a configurable missing-data strategy
5. Resample per station and device
6. Compute operational metrics
7. Persist metric results in SQLite using upsert semantics

The API returns structured processing metadata and exposes stored metrics through read endpoints. The LLM layer operates only on structured computed data or structured quality findings.

---

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
├── README.md
└── uv.lock
```

---

## Architecture

### 1. Ingestion library

* `src/air_platform/ingestion/repositories/base.py` – raw data repository contract
* `src/air_platform/ingestion/repositories/sqlite.py` – SQLite implementation for station data
* `src/air_platform/ingestion/schema_loader.py` – JSON schema parsing
* `src/air_platform/ingestion/validators.py` – required-column, type, and range validation
* `src/air_platform/ingestion/quality.py` – missing percentages, timestamp gaps, and flatline detection
* `src/air_platform/ingestion/cleaners.py` – missing-data handling strategies
* `src/air_platform/ingestion/resampling.py` – grouped time-series resampling
* `src/air_platform/ingestion/pipeline.py` – orchestration returning a `ProcessedDataset`

### 2. Metrics engine

* `src/air_platform/metrics/engine.py` – pure metric computation from `ProcessedDataset`
* `src/air_platform/metrics/models.py` – typed metric config, results, and query filters
* `src/air_platform/metrics/definitions.py` – metric metadata and units

### 3. API and storage

* `src/air_platform/storage/base.py` – metric storage contract
* `src/air_platform/storage/sqlite.py` – SQLite metric store with upsert semantics
* `src/air_platform/service/orchestrator.py` – service-layer orchestration
* `src/air_platform/service/routes.py` – thin FastAPI routes
* `src/air_platform/service/schemas.py` – Pydantic v2 request and response models

### 4. LLM integration layer

* `src/air_platform/llm/provider.py` – `LLMProvider` protocol; application code depends only on this abstraction
* `src/air_platform/llm/openai_provider.py` – OpenAI implementation with retry, timeout, and backoff
* `src/air_platform/llm/prompts.py` – centralized prompt templates
* `src/air_platform/llm/schemas.py` – `StructuredMetricQuery` bounded DSL for natural-language questions
* `src/air_platform/llm/use_cases.py` – application use cases for station summaries, NL queries, and quality reports

---

## Configuration

Optional environment overrides:

* `AIR_PLATFORM_SENSOR_DB_PATH`
* `AIR_PLATFORM_SENSOR_SCHEMA_PATH`
* `AIR_PLATFORM_METRICS_DB_PATH`
* `AIR_PLATFORM_DEFAULT_RESAMPLE_FREQUENCY`
* `AIR_PLATFORM_DEFAULT_MISSING_STRATEGY`
* `AIR_PLATFORM_DEFAULT_FLATLINE_WINDOW_MINUTES`
* `AIR_PLATFORM_ACTIVE_RPM_THRESHOLD`
* `AIR_PLATFORM_SPECIFIC_POWER_FLOW_THRESHOLD`

By default, the API reads from `data/sensor_data.db` and `data/sensor_schema.json`, and creates `data/metrics.db` on first write.

### OpenAI / LLM settings

| Environment variable                  | Default       | Description                                   |
| ------------------------------------- | ------------- | --------------------------------------------- |
| `AIR_PLATFORM_OPENAI_API_KEY`         | *(none)*      | Required for LLM endpoints and live LLM tests |
| `AIR_PLATFORM_OPENAI_MODEL`           | `gpt-4o-mini` | Model used for all LLM calls                  |
| `AIR_PLATFORM_OPENAI_TIMEOUT_SECONDS` | `30.0`        | Per-call timeout budget in seconds            |
| `AIR_PLATFORM_OPENAI_MAX_RETRIES`     | `3`           | Max retry attempts on transient failures      |

Retries use exponential backoff with jitter. Non-transient failures such as bad input or schema validation errors are not retried.

---

## LLM behavior: disabled vs degraded

There are two distinct LLM states worth calling out:

### 1. LLM disabled

If `AIR_PLATFORM_OPENAI_API_KEY` is not set:

* the API still starts
* deterministic ingestion and metrics endpoints still work
* LLM-powered endpoints return `503`

### 2. LLM degraded

If the API key is set but the OpenAI call fails after retries:

* the request does not crash unnecessarily
* endpoints return structured deterministic data where possible
* the response includes fields such as `llm_failed=true` and a warning message

This keeps the deterministic system usable even when the language layer is unavailable.

---

## Common commands

```bash
make install
make lint
make format
make typecheck
make test
make run
```

Local verification used during development:

```bash
uv run ruff check .
uv run mypy src tests
uv run pytest
```

---

## API

### `GET /health`

Readiness check.

Response:

```json
{"status": "ok"}
```

---

### `POST /stations/{station_id}/process`

Runs ingestion, cleaning, resampling, metric computation, and persistence for a station within a time window.

Example request:

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

* `start_time`
* `end_time`
* `resample_frequency`
* `missing_strategy` – one of `drop`, `fill`, `interpolate`
* `flatline_window_minutes`
* `active_rpm_threshold`
* `specific_power_flow_threshold`

Example response shape:

```json
{
  "station_id": "d43f07f0-0170-5663-a459-04597edb38b6",
  "window_start": "2024-02-01T00:00:00+00:00",
  "window_end": "2024-02-01T06:00:00+00:00",
  "rows_read": 720,
  "rows_after_cleaning": 684,
  "metrics_persisted": 42,
  "missing_percentages": {
    "air_flow_rate": 2.1,
    "power_consumption": 0.8
  },
  "warnings": [
    "Out-of-range values were converted to null",
    "Timestamp gaps detected for one device"
  ]
}
```

---

### `GET /metrics`

Reads persisted metrics with optional filters.

Supported query parameters:

* `station_id`
* `device_id`
* `start_time`
* `end_time`
* `metric_name`

Example request:

```bash
curl "http://127.0.0.1:8000/metrics?station_id=d43f07f0-0170-5663-a459-04597edb38b6&metric_name=average_pressure_bar"
```

Example response shape:

```json
[
  {
    "station_id": "d43f07f0-0170-5663-a459-04597edb38b6",
    "device_id": "compressor_1",
    "metric_name": "average_pressure_bar",
    "metric_value": 8.34,
    "unit": "bar",
    "window_start": "2024-02-01T00:00:00+00:00",
    "window_end": "2024-02-01T06:00:00+00:00",
    "computed_at": "2024-02-01T06:01:00+00:00",
    "resample_frequency": "30min",
    "missing_strategy": "fill"
  }
]
```

---

## LLM-powered endpoints

The following endpoints require `AIR_PLATFORM_OPENAI_API_KEY`.

The LLM is used only for:

* narrating already-computed metrics
* narrating already-detected data quality findings
* parsing a natural-language question into a validated structured query

The LLM is **not** used to compute metrics.

---

### `POST /stations/{station_id}/summary`

Fetches stored metrics for a station and generates a plain-English health summary.

Metrics are read from storage deterministically; the LLM only narrates them.

Example request:

```bash
curl -X POST http://127.0.0.1:8000/stations/d43f07f0-0170-5663-a459-04597edb38b6/summary \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2024-02-01T00:00:00+00:00",
    "end_time": "2024-02-01T06:00:00+00:00"
  }'
```

Response shape:

```json
{
  "station_id": "d43f07f0-0170-5663-a459-04597edb38b6",
  "summary": "Station ran at 78% uptime with average pressure of 8.3 bar and stable flow during the selected period.",
  "metrics": [
    {
      "device_id": "compressor_1",
      "metric_name": "average_pressure_bar",
      "metric_value": 8.34,
      "unit": "bar"
    }
  ],
  "llm_failed": false,
  "warning": null
}
```

If the OpenAI call fails after retries, the endpoint still returns the structured `metrics` payload with `llm_failed=true`.

---

### `POST /llm/query`

Accepts a plain-English question about metrics and returns a deterministic answer plus an optional natural-language rendering.

Flow:

1. OpenAI parses the question into a `StructuredMetricQuery`
2. The application validates the parsed query
3. The application executes the query deterministically against stored metrics
4. OpenAI may phrase the numeric result in English

The model is not allowed to answer directly from its own reasoning.

Example request:

```bash
curl -X POST http://127.0.0.1:8000/llm/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "What was the average pressure for station d43f07f0 last week?"
  }'
```

Response shape:

```json
{
  "original_question": "What was the average pressure for station d43f07f0 last week?",
  "parsed_query": {
    "station_id": "d43f07f0-0170-5663-a459-04597edb38b6",
    "metric_name": "average_pressure_bar",
    "aggregation": "mean",
    "needs_clarification": false,
    "clarification_message": null
  },
  "aggregate_value": 8.34,
  "natural_language_answer": "The average discharge pressure was 8.34 bar.",
  "llm_rendering_failed": false,
  "warning": null
}
```

If the question is ambiguous, for example when no station is specified, the response sets `needs_clarification=true` and explains what is missing. No metric query is executed in that case.

---

### `POST /stations/{station_id}/quality-report`

Runs the ingestion pipeline to detect data quality issues, then generates a plain-English narrative. The LLM only narrates pre-computed structured findings.

Example request:

```bash
curl -X POST http://127.0.0.1:8000/stations/d43f07f0-0170-5663-a459-04597edb38b6/quality-report \
  -H "Content-Type: application/json" \
  -d '{
    "start_time": "2024-02-01T00:00:00+00:00"
  }'
```

Response shape:

```json
{
  "station_id": "d43f07f0-0170-5663-a459-04597edb38b6",
  "report": "Data quality for this period is acceptable. Two timestamp gaps were found and one flatline event was detected.",
  "total_rows_read": 1440,
  "total_rows_after_cleaning": 1432,
  "column_missing_pct": {
    "discharge_pressure": 0.5
  },
  "gap_count": 2,
  "flatline_count": 1,
  "warnings": [],
  "llm_failed": false,
  "llm_warning": null
}
```

If the OpenAI call fails after retries, the endpoint still returns the structured quality findings with `llm_failed=true`.

---

## Processing behavior

### Validation

The pipeline fails fast for:

* missing required columns
* unreadable schema
* no station data found
* all timestamps unreadable
* no usable rows after cleaning or resampling

The following are reported as quality findings rather than hard failures:

* malformed numeric values coerced to null
* out-of-range values
* timestamp gaps
* flatline periods
* per-column missing percentages

### Cleaning strategy

Chosen behavior:

* numeric columns are coerced with `pandas.to_numeric(errors="coerce")`
* out-of-range values are converted to null and counted in the quality report
* missing-data handling is explicit and configurable:

  * `drop` – remove rows with missing sensor values
  * `fill` – forward-fill then backfill per device
  * `interpolate` – time-based interpolation per device

Default service setting: `fill`

### Resampling

Resampling is performed per `station_id` and `device_id` using mean aggregation for:

* `discharge_pressure`
* `air_flow_rate`
* `power_consumption`
* `motor_speed`
* `discharge_temp`

This keeps timestamp alignment explicit and easy to explain.

### Data quality report

Each processing run returns:

* rows read
* rows after cleaning
* per-column missing percentages
* out-of-range counts
* malformed value counts
* timestamp gap details
* flatline period details
* warning summary strings

Flatline detection uses the greater of:

* the request-level flatline window
* sensor-specific thresholds defined in `sensor_schema.json`

---

## Metric definitions

Metrics are computed per device:

* **`active_duration_hours`**
  Active time where `motor_speed > active_rpm_threshold`

* **`active_ratio_pct`**
  Active sample ratio over the processed window

* **`average_pressure_bar`**
  Mean `discharge_pressure` after cleaning and resampling

* **`peak_pressure_bar`**
  Max `discharge_pressure` after cleaning and resampling

* **`mean_specific_power_kw_per_m3h`**
  Mean of `power_consumption / air_flow_rate` for rows where flow is above `specific_power_flow_threshold`

* **`cycle_count`**
  Count of inactive-to-active transitions within the observed window

* **`total_flow_volume_m3`**
  Sum of `air_flow_rate * interval_hours` across the resampled series

Stored metric records include:

* `station_id`
* `device_id`
* `metric_name`
* `metric_value`
* `unit`
* `window_start`
* `window_end`
* `computed_at`
* `resample_frequency`
* `missing_strategy`

---

## Tests

The test suite is split by layer:

* `tests/unit` – validation, cleaning, quality, resampling, and metric logic
* `tests/integration` – SQLite repository behavior, pipeline execution, metric persistence, and coarse OpenAI-backed integration checks
* `tests/api` – FastAPI endpoint behavior, request/response validation, and endpoint-level checks

### LLM testing approach

This project intentionally uses **real OpenAI API calls** for the LLM layer rather than mocked provider tests.

That choice is deliberate:

* it validates the actual provider integration path
* it verifies real structured extraction against the OpenAI API
* it exercises retry, timeout, and degraded-response behavior against the live provider

Tradeoffs:

* these tests are slower than pure isolated tests
* they require network access and credentials
* they consume API tokens
* wording can vary, so assertions stay coarse-grained

Because of that, LLM-related tests do **not** assert exact phrasing. They assert things like:

* non-empty text responses
* valid structured schema output
* successful deterministic query execution around LLM parsing
* correct degraded behavior when provider calls fail

### Running tests

Run the default test suite:

```bash
make test
```

Run the full suite directly:

```bash
uv run pytest
```

Run live OpenAI-backed tests explicitly:

```bash
AIR_PLATFORM_OPENAI_API_KEY=sk-... uv run pytest -v
```

Or target only LLM-related tests:

```bash
AIR_PLATFORM_OPENAI_API_KEY=sk-... uv run pytest \
  tests/unit \
  tests/integration \
  tests/api -k "llm or openai" -v
```

If `AIR_PLATFORM_OPENAI_API_KEY` is not set, LLM-related tests should be skipped or fail fast according to the project’s current test configuration.

Covered cases include:

* missing required columns
* malformed and out-of-range values
* timestamp gap detection
* flatline detection
* missing-data strategies
* zero-flow specific power behavior
* cycle-count edge cases
* invalid station handling
* API retrieval filters
* OpenAI-backed structured extraction
* OpenAI-backed summary/report generation
* degraded behavior around LLM failures

---

## Design decisions and tradeoffs

* **Library-first over framework-first**
  Ingestion and metric logic can be reused by APIs, notebooks, background jobs, or alternative frontends without importing FastAPI.

* **SQLite behind interfaces**
  Raw input storage and metric output storage are abstracted so future migration to Postgres or another backend is a repository change rather than a pipeline rewrite.

* **Simple deterministic cleaning**
  `drop`, `fill`, and `interpolate` were chosen because they are explainable, easy to test, and sufficient for the assignment scope.

* **Typed outputs over loose DataFrames**
  The ingestion pipeline returns a structured `ProcessedDataset` with cleaning and quality metadata instead of only returning a bare DataFrame.

* **Practical idempotency**
  Metrics use a composite primary key and SQLite upsert so reprocessing the same window/config cleanly overwrites prior results.

* **LLM as language layer only**
  The LLM is explicitly forbidden from performing computation. It receives structured data and either narrates it or parses a user question into a bounded structured query. Metric correctness stays deterministic even if the model changes.

* **Provider abstraction for swappability**
  Application code depends on the provider abstraction, while OpenAI lives behind a concrete implementation. This makes future provider swaps possible without changing the metric logic.

* **Bounded DSL instead of free-form output**
  The NL query endpoint uses `StructuredMetricQuery`, a Pydantic model with constrained fields. The model cannot return SQL, code, or arbitrary executable instructions.

* **Graceful degradation over hard failures**
  Summary and report endpoints always prefer returning structured deterministic data with failure flags rather than crashing the whole request.

* **Live provider testing for the LLM layer**
  The repository tests the real OpenAI path for LLM features. This improves confidence in real-world integration at the cost of speed, determinism, and token consumption.

---

## Assumptions and limitations

* The project uses SQLite for both assignment input and metric persistence, which is appropriate for local development and the assignment scope but not the intended production datastore.
* Resampling currently uses mean aggregation for all supported numeric sensor fields; a production system might apply field-specific aggregation rules.
* Missing-data handling is intentionally simple and deterministic; more advanced imputation strategies were out of scope.
* The API writes computed metrics but does not include deployment, migrations, authentication, or multi-tenant concerns because those were not part of the assignment.
* LLM features depend on an external provider and are therefore subject to latency, availability, and token-cost considerations.

---

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

1. Build a Docker image for the FastAPI service
2. Push the image to a registry
3. Deploy to the target platform
4. Run smoke checks against `/health`
5. Apply storage migrations if the metric schema evolves

The repository intentionally stops at CI because deployment target details were not part of the assignment.