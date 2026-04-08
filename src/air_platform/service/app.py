"""FastAPI application entrypoint."""

from __future__ import annotations

import queue
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from air_platform import __version__
from air_platform.bootstrap.container import AppContainer
from air_platform.config import AppSettings
from air_platform.errors import (
    DataNotFoundError,
    LLMError,
    LLMNotConfiguredError,
    SchemaLoadError,
    StorageError,
    ValidationError,
)
from air_platform.service.routes import router


def create_app(
    settings: AppSettings | None = None,
    event_queue: queue.Queue[dict[str, Any] | None] | None = None,
) -> FastAPI:
    """Create the FastAPI application.

    Args:
        settings: Optional settings override (defaults to ``AppSettings()``).
        event_queue: Optional pre-created ``queue.Queue`` shared with a
            producer running in the same process.  See ``run_with_producer.py``.
            When *None*, the container creates its own private queue (the
            default for the standalone server with no producer wired in).
    """

    resolved_settings = settings or AppSettings()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        container = AppContainer.build(
            resolved_settings.sensor_schema_path,
            consumer_error_cap=resolved_settings.consumer_error_cap,
            event_queue=event_queue,
            queue_maxsize=resolved_settings.consumer_queue_maxsize,
        )
        _app.state.container = container
        container.start_consumer()
        try:
            yield
        finally:
            container.stop_consumer()

    app = FastAPI(
        title="Air Platform Metrics Service",
        version=__version__,
        lifespan=lifespan,
    )
    app.state.settings = resolved_settings
    app.include_router(router)

    @app.exception_handler(DataNotFoundError)
    async def handle_not_found(_: Request, exc: DataNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    # Server-fault errors: the client sent a valid request but the server cannot
    # fulfil it due to a missing DB, locked file, or unreadable schema.  503 is
    # correct here — these are not client mistakes (422 would be wrong).
    async def handle_server_fault(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    app.add_exception_handler(SchemaLoadError, handle_server_fault)
    app.add_exception_handler(StorageError, handle_server_fault)

    async def handle_validation_error(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    app.add_exception_handler(ValidationError, handle_validation_error)

    @app.exception_handler(LLMNotConfiguredError)
    async def handle_llm_not_configured(_: Request, exc: LLMNotConfiguredError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(LLMError)
    async def handle_llm_error(_: Request, exc: LLMError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    return app


app = create_app()
