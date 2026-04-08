"""Run the API server together with the SensorEventProducer in a single process.

Because ``queue.Queue`` is an in-process data structure, the producer and the
API consumer *must share the same queue instance in the same Python process*.
This script creates that shared queue, wires the producer to it, and passes it
into ``create_app()`` so the API's background consumer reads from the same
source.

Usage::

    uv run python run_with_producer.py

The server starts on http://127.0.0.1:8000 (same as ``make run``).
"""

from __future__ import annotations

import queue
from typing import Any

import uvicorn

from air_platform.config import AppSettings
from air_platform.service.app import create_app
from producer import SensorEventProducer


def main() -> None:
    """Wire queue + producer + app and start the server.

    All setup is deferred to this function so that merely *importing* this
    module does not start threads, open database connections, or build the
    FastAPI app — avoiding surprises in reloaders, test collectors, and
    accidental imports.
    """
    settings = AppSettings()

    # 1. Create the shared queue — both producer and consumer use this instance.
    #    Bounded by consumer_queue_maxsize to apply backpressure if the consumer lags.
    shared_queue: queue.Queue[dict[str, Any] | None] = queue.Queue(
        maxsize=settings.consumer_queue_maxsize
    )

    # 2. Start the producer in a background daemon thread.
    producer = SensorEventProducer(
        db_path=str(settings.sensor_db_path),
        event_queue=shared_queue,
    )
    producer.start()

    # 3. Build the FastAPI app, injecting the shared queue into the container.
    app = create_app(settings=settings, event_queue=shared_queue)
    # Expose the producer on app.state so /health can surface stream failures.
    app.state.producer = producer

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
