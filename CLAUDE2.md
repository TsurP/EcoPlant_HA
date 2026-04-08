# CLAUDE.md

## Project context

This repository already contains the implementation for:

- Challenge 1: sensor data validation, preprocessing, aggregation, and query API
- Challenge 2: LLM-powered endpoints on top of the metrics service

Your task is to implement **Challenge 3 — Event-Driven Consumer** on top of the existing codebase, without rewriting working Challenge 1/2 functionality.

The goal is to add an event-driven ingestion path that reuses the same domain processing pipeline already used elsewhere in the project.

---

## Core architectural rule

**Do not put business logic in the queue consumer or transport layer.**

The architecture must remain:

**Transport -> Parse -> Domain Processing -> Repositories -> Query API**

This means:

- queue-specific code belongs in `transport/`
- message orchestration belongs in `ingestion/`
- sensor validation, preprocessing, and aggregation remain in `domain/`
- storage concerns remain in `repositories/`
- HTTP exposure remains in `api/`

The consumer is only another entrypoint into the same core processing pipeline.

---

## Existing repo assumptions

Assume the project already uses:

- Python
- uv
- FastAPI
- pytest
- typed models and clean module boundaries
- a reusable Challenge 1 processing pipeline
- a main FastAPI application that should be extended, not replaced

If names differ slightly in the repo, preserve the existing naming conventions.

---

## What to implement

Implement Challenge 3 by adding:

1. A transport abstraction for consuming events
2. An in-memory queue transport adapter compatible with `producer.py`
3. An event handler that parses raw queue events and routes them into the existing Challenge 1 processing pipeline
4. Incremental aggregate updates stored in repositories
5. Processing status and recent error tracking
6. FastAPI endpoints for:
   - querying aggregated metrics with filters
   - viewing processing status
   - viewing recent processing errors
7. Tests covering unit and integration behavior

---

## Required directory structure

Use or adapt the repo toward this structure:

```text
src/ecoplant/
  main.py
  config.py

  api/
    deps.py
    routes_health.py
    routes_metrics.py
    routes_processing.py
    routes_llm.py

  domain/
    models.py
    validation.py
    preprocessing.py
    aggregation.py
    processing.py
    query.py

  ingestion/
    event_models.py
    parser.py
    handler.py
    consumer.py
    status.py
    errors.py

  transport/
    base.py
    models.py
    in_memory_queue.py

  repositories/
    metrics.py
    processing_status.py
    errors.py

  services/
    metrics_service.py
    processing_service.py
    llm_service.py

  bootstrap/
    container.py
````

If equivalent modules already exist, extend them instead of duplicating them.

---

## Design requirements

### 1. Pluggable transport

Create a transport interface/protocol similar to:

```python
class MessageTransport(Protocol):
    def receive(self) -> TransportMessage | None: ...
    def ack(self, message: TransportMessage) -> None: ...
    def reject(self, message: TransportMessage, reason: str) -> None: ...
    def size(self) -> int | None: ...
```

Provide an implementation backed by Python `queue.Queue` for the supplied `producer.py`.

The rest of the ingestion code must depend only on the interface, not directly on `queue.Queue`.

### 2. Shared domain processing

The consumer must reuse the same Challenge 1 validation, preprocessing, and aggregation logic.

Do not duplicate validation rules inside the consumer.

### 3. Normalized internal models

Introduce explicit separation between:

* raw queue event models
* internal sensor reading/domain models

Suggested flow:

* raw transport message
* raw event payload model
* parser/mapper
* internal `SensorReading`
* domain processing

### 4. Incremental aggregate storage

Store aggregates incrementally in a repository keyed by dimensions such as:

* station_id
* device_id
* metric_type
* bucket_start

Recommended aggregate values:

* count
* min
* max
* avg
* latest_timestamp

Support at least `hour` and `day` buckets if practical. If only one bucket is feasible in the current timeframe, implement `hour` first but keep the design extensible.

### 5. Graceful error handling

The consumer loop must never crash because of one malformed event.

Introduce typed errors such as:

* `MalformedEventError`
* `EventValidationError`
* `EventProcessingError`
* `TransportError`

Behavior requirements:

* malformed events are recorded and rejected
* validation failures are recorded and rejected
* processing failures are recorded and rejected
* transport failures are logged/recorded without killing the process

### 6. Processing status

Track at least:

* consumer_running
* events_consumed
* events_processed_successfully
* events_malformed
* events_failed
* last_event_timestamp
* last_success_timestamp
* last_error_timestamp
* queue_depth if available

Also store a capped list of recent errors.

---

## API requirements

Extend the current FastAPI app.

### Metrics query endpoint

Provide or extend a metrics endpoint so that aggregated metrics can be filtered by:

* station
* optional time range
* optional device
* optional metric type
* optional bucket

One acceptable shape is:

* `GET /metrics/stations/{station_id}`

with query parameters:

* `device_id`
* `metric_type`
* `start_time`
* `end_time`
* `bucket`

### Processing status endpoint

Add:

* `GET /processing/status`

### Processing errors endpoint

Add:

* `GET /processing/errors`

Responses should be typed and consistent with existing API style.

---

## Runtime model

For this assignment, prefer a **single-process demo architecture**:

* FastAPI app starts
* shared repositories/services are constructed once
* consumer starts as a background task/thread on app startup
* the in-memory queue transport reads from the same queue used by `producer.py`

This is the simplest way to make in-memory state visible to the API.

However, structure the code so the consumer can also be started independently later.

---

## Repository guidance

Use interfaces or at least clearly separated classes for repositories.

Recommended repositories:

* `MetricsRepository`
* `ProcessingStatusRepository`
* `ErrorRepository`

Implement in-memory versions first.

Metrics repository should support:

* upsert/update aggregate
* filtered query by station/device/metric_type/time range/bucket

Status repository should support:

* increment counters
* set timestamps
* get current status snapshot

Error repository should support:

* append recent error
* return capped recent list

---

## Suggested main services

Implement thin services/facades where useful:

* `DomainProcessingService`
* `EventHandler`
* `ConsumerRunner`
* `MetricsQueryService`
* `ProcessingStatusService`

The most important rule is clean responsibility separation, not exact class names.

---

## Consumer behavior

The consume loop should roughly do:

1. receive message from transport
2. record that an event was consumed
3. parse raw payload
4. map to internal domain model
5. call domain processing pipeline
6. on success:

   * update status
   * ack message
7. on failure:

   * record structured error
   * reject message
   * continue loop

Do not let one bad event stop the loop.

---

## Testing requirements

Add tests that match the current project’s testing style.

### Unit tests

Cover at least:

* event parsing and validation
* aggregate updates
* query filtering
* handler success flow
* handler malformed-event flow
* consumer ack/reject behavior

### Integration tests

Cover at least:

* end-to-end queue -> consumer -> repository -> API flow
* `/processing/status`
* `/processing/errors`
* metrics query endpoint with filters

If the existing repo already has API test fixtures, reuse them.

Do not introduce mock-heavy tests unless the repo already uses that style. Prefer lightweight real-object tests with in-memory repositories and queue.

---

## Code quality expectations

Maintain project standards:

* strong type hints
* small focused modules
* clear docstrings where useful
* no dead code
* no duplicate business logic
* preserve existing style/tooling
* keep imports and naming consistent with the repo

If the repo already uses:

* ruff
* mypy / pyright
* pytest
* pydantic

then continue using them consistently.

---

## Deliverables

Implement the feature end-to-end so that the repository supports:

1. running the API
2. starting a background consumer
3. reading events from the provided producer queue
4. updating aggregated metrics
5. exposing queryable metrics and processing diagnostics via API
6. passing tests

---

## Non-goals

Do not add:

* Kafka
* Redis Streams
* external infrastructure
* a database migration layer
* Docker rearchitecture
* complex retry orchestration
* dead-letter queue infrastructure beyond a simple recorded reject/error mechanism

The design should be extensible to those later, but the implementation should remain appropriate for the assignment.

---

## Implementation order

Use this order:

1. inspect existing Challenge 1 processing pipeline and identify the single reusable processing entrypoint
2. add transport abstractions and in-memory queue adapter
3. add raw event models and parser
4. add repositories for metrics/status/errors
5. add event handler
6. add consumer loop
7. wire shared dependencies in bootstrap/container
8. extend FastAPI routes
9. add startup wiring for background consumer
10. add tests
11. update README with Challenge 3 usage

---

## README updates expected

After implementation, update the README to include:

* architecture overview
* Challenge 3 design
* how to run the API
* how to run the producer/consumer demo
* available endpoints
* test commands
* note that the queue transport is swappable by replacing the transport adapter only

---

## Final quality bar

The result should look like a production-minded assignment submission:

* clean architecture
* easy to explain in an interview
* minimal duplication
* obvious extension path to Redis Streams / PubSub
* simple local demo flow

````

---

# Small adjustments I’d make if your current repo differs

If your current repo already uses `app/` instead of `src/ecoplant/`, then keep it like this:

```text
app/
  api/
  domain/
  ingestion/
  transport/
  repositories/
  services/
````

If your current Challenge 1 code already has names like:

* `schemas.py`
* `processor.py`
* `storage.py`

then extend those rather than forcing the exact filenames above.

The important thing is the **boundary**, not the exact label.