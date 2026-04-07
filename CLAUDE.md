## Goal

Implement a production-quality Python project for the following assignment:

- Build a reusable **data ingestion and transformation library**
- Build a thin **API metrics service** on top of it
- Add **tests**, **automation**, and a strong **README**
- Keep the architecture clean, typed, testable, and easy to explain

This repository should look like something an AI Engineer would submit in a real interview.

---

## Core design principles

1. **Library-first design**
   - The ingestion/transformation logic must live in a standalone Python package.
   - It must not depend on any web framework.

2. **Thin service layer**
   - The API service should orchestrate calls into the library.
   - The API must not contain business logic.

3. **Storage abstraction**
   - Reading raw sensor data must go through an interface / repository abstraction.
   - The current implementation may use SQLite, but the design should make it easy to swap to BigQuery/Postgres later.

4. **Typed and testable**
   - Use type hints throughout.
   - Keep functions small and deterministic.
   - Separate pure logic from I/O.

5. **Simple over clever**
   - Prefer a clean, explainable solution over over-engineering.
   - Avoid unnecessary frameworks, async complexity, or heavy infrastructure.

---

## Required stack

Use the following unless there is a very strong reason not to:

- **Python 3.12**
- **uv** for dependency management
- **ruff** for linting and formatting
- **mypy** for type checking
- **pytest** for tests
- **FastAPI** for the API service
- **pandas** for tabular/time-series processing
- **Pydantic v2** for request/response/config models
- **Makefile** for common commands

Keep the dependency set small and modern.

---

## Expected repository structure

Use a `src/` layout and keep module boundaries clear.

Suggested structure:

```text
.
├── CLAUDE.MD
├── README.md
├── pyproject.toml
├── uv.lock
├── Makefile
├── .gitignore
├── src/
│   └── air_platform/
│       ├── __init__.py
│       ├── config.py
│       ├── ingestion/
│       │   ├── __init__.py
│       │   ├── models.py
│       │   ├── schema_loader.py
│       │   ├── validators.py
│       │   ├── quality.py
│       │   ├── cleaners.py
│       │   ├── resampling.py
│       │   ├── pipeline.py
│       │   └── repositories/
│       │       ├── __init__.py
│       │       ├── base.py
│       │       └── sqlite.py
│       ├── metrics/
│       │   ├── __init__.py
│       │   ├── definitions.py
│       │   ├── engine.py
│       │   ├── models.py
│       │   └── repositories.py
│       ├── service/
│       │   ├── __init__.py
│       │   ├── app.py
│       │   ├── dependencies.py
│       │   ├── routes.py
│       │   └── schemas.py
│       └── storage/
│           ├── __init__.py
│           ├── base.py
│           └── sqlite.py
├── tests/
│   ├── unit/
│   ├── integration/
│   └── api/
└── data/
    ├── sensor_data.db
    └── sensor_schema.json
````

You may adjust names slightly, but keep the same separation of concerns.

---

## Part 0 — Project setup requirements

Implement the project as a polished Python repository.

### Must include

* Reproducible dependency installation with `uv`
* `pyproject.toml` with all project/tool config
* `ruff` configured for lint + format
* `mypy` configured and passing
* `pytest` configured
* `Makefile` with common commands
* `README.md` with setup and usage instructions

### Makefile commands

At minimum, support:

* `make install`
* `make lint`
* `make format`
* `make typecheck`
* `make test`
* `make run`

These should be simple wrappers around `uv` commands.

---

## High-level architecture

The system must have 3 clear layers:

### 1. Ingestion library

Responsible for:

* reading sensor data
* validating against schema
* cleaning missing/malformed values
* resampling
* generating a data quality report
* returning structured processed output

### 2. Metrics engine

Responsible for:

* computing operational metrics from the processed dataset
* being independent from FastAPI
* producing clearly defined metric results

### 3. API service

Responsible for:

* exposing endpoints
* invoking the ingestion library + metrics engine
* storing and retrieving computed metrics
* health checks

---

## Ingestion library design

### Design rule

Treat the ingestion library as a reusable internal package that could later be imported by:

* an API service
* a batch job
* a notebook
* a worker
* another microservice

Do not couple it to FastAPI.

### Required responsibilities

The ingestion library must:

1. Read sensor data from SQLite
2. Read station metadata if needed
3. Load the JSON schema
4. Validate:

   * required columns
   * data types
   * value ranges
5. Detect and report quality issues:

   * missing values %
   * out-of-range values
   * gaps in timestamps
   * flatline periods
6. Apply configurable missing/malformed-data handling
7. Resample to a configurable frequency
8. Return clean structured output

### Repository abstraction

Define an interface / protocol / abstract base class for raw data access.

Example conceptually:

* `SensorDataRepository`

  * fetch readings for station
  * fetch readings with optional time range
  * fetch metadata for station

Implement a SQLite-backed adapter now.

Important: consumers of the ingestion library should not care whether data comes from SQLite, BigQuery, or Postgres.

---

## Library output contract

The ingestion pipeline should return a structured object, not just a bare DataFrame.

It should contain at least:

* processed sensor data
* station identifier
* time range used
* resample frequency used
* quality report
* summary stats about cleaning

A good shape is something like:

* `ProcessedDataset`
* `QualityReport`
* `ValidationResult`

These names can vary, but the idea should stay the same.

---

## Validation behavior

Implement clear validation rules.

### Hard failures

These should fail processing:

* missing required columns
* unreadable schema
* invalid station identifier / no data found
* completely unusable timestamps
* critical type/schema mismatch that prevents processing

### Quality issues / warnings

These should be reported, not necessarily fail:

* partial missing values
* out-of-range sensor values
* flatline segments
* timestamp gaps
* malformed values that can be coerced
* sparse devices

### Range handling

Use the provided `sensor_schema.json` as source of truth for:

* expected columns
* types
* valid ranges

If a value is outside the allowed range:

* record it in the quality report
* decide whether to null it, drop it, or retain it based on the chosen strategy
* document the chosen behavior

---

## Cleaning behavior

Make cleaning configurable.

### Required supported strategies

Support configurable strategies for missing/malformed values, such as:

* `drop`
* `fill`
* `interpolate`

You do not need to support every possible combination, but the design should be explicit and configurable.

### Recommended behavior

A good default behavior is:

* coerce numeric columns where possible
* convert impossible values to null
* report them in the quality report
* apply a selected missing-data strategy
* resample after validation/cleaning

### Config

Represent processing behavior with a config object, such as:

* station id
* start/end time
* resample frequency
* missing strategy
* flatline detection threshold/window
* active-state thresholds for metrics if needed

Keep this typed and explicit.

---

## Data quality reporting

The quality report is an important deliverable.

Include at least:

* total rows read
* total rows after cleaning
* per-column missing %
* out-of-range count per relevant column
* malformed/coerced value counts
* detected timestamp gaps
* detected flatline periods
* warnings list / issue list

Flatline detection should be simple and explainable:

* detect long consecutive periods where a signal remains constant
* make the minimum flatline duration configurable

---

## Resampling

Support configurable resampling frequency.

### Requirements

* resample to a configurable interval
* preserve station/device grouping
* use a documented aggregation strategy

### Suggested aggregation logic

For time-series metrics, a reasonable default is:

* pressure, flow, power, rpm, temperature: aggregate by mean during resampling
* keep timestamp aligned to the requested interval
* do this per station/device

Document the resampling assumptions in the README.

---

## Metrics engine

Implement metric computation as a separate module.

It should consume the processed output from the ingestion library and return structured metric results.

### Required metrics

Implement at least 4. Prefer 5.

Recommended set:

1. **Uptime / active time per device**
2. **Average pressure**
3. **Peak pressure**
4. **Specific power**
5. **Cycle count**
6. **Total flow volume**

You may implement 5 of these.

### Metric definitions

Document them clearly and implement them consistently.

Recommended definitions:

#### 1. Uptime / active time

Define a device as active when it crosses a configurable threshold, for example:

* `rpm > active_rpm_threshold`, or
* `power_kw > active_power_threshold`

Use one consistent rule and document it.

Output:

* active duration
* optionally active ratio over the requested period

#### 2. Average pressure

Mean of `pressure_bar` over the selected window after cleaning/resampling.

#### 3. Peak pressure

Maximum `pressure_bar` over the selected window.

#### 4. Specific power

`power_kw / flow_m3h`

Important:

* only compute when flow is positive / above a small threshold
* avoid division by zero
* document whether you report mean specific power or another aggregation

#### 5. Cycle count

Count inactive→active transitions over time for each device.

#### 6. Total flow volume

Integrate `flow_m3h` over time.

For example:

* if data is resampled to regular intervals, convert flow rate to volume over each interval and sum across the window

### Metric result shape

Store results with enough metadata, for example:

* station_id
* device_id
* metric_name
* metric_value
* unit
* window_start
* window_end
* computed_at

---

## Metrics storage

Persist computed metrics in a dedicated results store.

Use SQLite for this assignment, but abstract it behind a repository interface.

### Required behavior

* save computed metrics after processing
* retrieve computed metrics with optional filters:

  * station
  * device
  * time range
  * metric name

### Nice-to-have

Make processing reasonably idempotent for the same station/time window/config.
A simple overwrite or upsert strategy is acceptable.

---

## API service

Use FastAPI.

### Endpoints

Implement the following:

#### 1. Process station endpoint

Triggers processing for a station:

* load raw data
* validate + clean + resample
* compute metrics
* store results
* return a summary response

Recommended route:

* `POST /stations/{station_id}/process`

Allow optional request body / query params for:

* time range
* resample frequency
* cleaning strategy

#### 2. Retrieve metrics endpoint

Returns previously computed metrics for a station.

Recommended route:

* `GET /metrics`

Support filters such as:

* `station_id`
* `device_id`
* `start_time`
* `end_time`
* `metric_name`

#### 3. Health endpoint

Recommended route:

* `GET /health`

Return a simple healthy response.

### Service rule

Route handlers should remain thin.
Put orchestration in service functions, not in route files.

---

## Testing strategy

Tests should be split into clear layers.

### 1. Unit tests

Fast and isolated.

Cover:

* schema validation
* missing-data strategies
* range validation
* flatline detection
* gap detection
* resampling logic
* each metric formula

### 2. Integration tests

Use real SQLite test databases / fixtures.

Cover:

* SQLite repository reading raw data
* full ingestion pipeline
* metrics persistence and retrieval

### 3. API tests

Use FastAPI test client.

Cover:

* health endpoint
* process endpoint happy path
* process endpoint error path
* retrieve metrics endpoint with filters

### Test organization

Use:

* `tests/unit`
* `tests/integration`
* `tests/api`

Keep fixtures reusable and minimal.

### Important test cases

Make sure the test suite includes:

* missing required columns
* out-of-range sensor values
* missing timestamps / gaps
* flatline signal segments
* zero-flow rows for specific power
* cycle counting edge cases
* empty result sets / invalid station id
* station with multiple devices

---

## CI/CD expectations

Include a short CI/CD section in the README.

### CI

Describe a pipeline that does:

1. install dependencies
2. lint
3. format check
4. type check
5. run tests

A GitHub Actions workflow is ideal.

### CD

A brief production-minded description is enough:

* build Docker image
* push image
* deploy API service
* run smoke/health checks
* use migrations if storage evolves

You do not need to fully implement deployment unless it is easy, but the CI workflow should exist.

---

## README requirements

The README must be strong and evaluator-friendly.

Include:

1. **Project overview**
2. **Architecture summary**
3. **Setup instructions**
4. **How to run checks**
5. **How to run tests**
6. **How to start the API**
7. **Endpoint summary**
8. **Metric definitions**
9. **Design decisions and tradeoffs**
10. **What a CI/CD pipeline looks like**

A new developer should be able to clone the repo, install dependencies, and run tests quickly.

---

## Quality bar

The final submission should feel:

* organized
* typed
* documented
* easy to review
* easy to explain in an interview

The evaluator should clearly see:

* good project structure
* separation of concerns
* reusable library design
* thin API layer
* layered tests
* production-oriented thinking

---

## Implementation constraints

* No unnecessary async complexity
* No business logic inside FastAPI routes
* No tight coupling between ingestion code and SQLite details
* No coupling between ingestion code and FastAPI
* No giant god-module
* No hidden magic behavior
* No over-engineered abstractions with no practical value

Use abstractions only where they improve swapability, testability, or clarity.

---

## Suggested implementation order

Follow this order:

1. Initialize project and tooling
2. Create repository structure and package layout
3. Implement ingestion domain models/config
4. Implement SQLite raw data repository
5. Implement schema loading and validation
6. Implement cleaning + resampling + quality reporting
7. Implement processed dataset output contract
8. Implement metrics definitions and engine
9. Implement metrics results storage
10. Implement FastAPI service and routes
11. Write unit tests
12. Write integration tests
13. Write API tests
14. Write README
15. Add CI workflow

---

## Final instruction

Implement the full repository end-to-end.
Do not stop at scaffolding.
Produce a complete, runnable, well-structured submission with:

* working ingestion library
* working API service
* tests
* automation
* documentation

When in doubt, choose the simpler architecture that best demonstrates sound engineering judgment.