"""FastAPI application entrypoint."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from air_platform import __version__
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


def create_app(settings: AppSettings | None = None) -> FastAPI:
    """Create the FastAPI application."""

    app = FastAPI(title="Air Platform Metrics Service", version=__version__)
    app.state.settings = settings or AppSettings()
    app.include_router(router)

    @app.exception_handler(DataNotFoundError)
    async def handle_not_found(_: Request, exc: DataNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    async def handle_domain_errors(_: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    app.add_exception_handler(SchemaLoadError, handle_domain_errors)
    app.add_exception_handler(StorageError, handle_domain_errors)
    app.add_exception_handler(ValidationError, handle_domain_errors)

    @app.exception_handler(LLMNotConfiguredError)
    async def handle_llm_not_configured(_: Request, exc: LLMNotConfiguredError) -> JSONResponse:
        return JSONResponse(status_code=503, content={"detail": str(exc)})

    @app.exception_handler(LLMError)
    async def handle_llm_error(_: Request, exc: LLMError) -> JSONResponse:
        return JSONResponse(status_code=502, content={"detail": str(exc)})

    return app


app = create_app()
