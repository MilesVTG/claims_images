"""Exception handler middleware that logs errors to the error_logs table.

Additive — does not replace or interfere with existing logging.
Worker-side copy uses worker's own database session.
"""

import logging
import traceback as tb
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.database import SessionLocal

logger = logging.getLogger(__name__)


def _log_error_to_db(
    service: str,
    endpoint: str,
    method: str,
    status_code: int,
    error_type: str,
    message: str,
    traceback_str: str,
    request_id: str,
    pipeline_stage: str | None = None,
):
    """Write an error record to the error_logs table."""
    try:
        db = SessionLocal()
        try:
            db.execute(
                text("""
                    INSERT INTO error_logs
                        (service, endpoint, method, status_code,
                         error_type, message, traceback, request_id, pipeline_stage)
                    VALUES
                        (:service, :endpoint, :method, :status_code,
                         :error_type, :message, :traceback, :request_id, :pipeline_stage)
                """),
                {
                    "service": service,
                    "endpoint": endpoint,
                    "method": method,
                    "status_code": status_code,
                    "error_type": error_type,
                    "message": message,
                    "traceback": traceback_str,
                    "request_id": request_id,
                    "pipeline_stage": pipeline_stage,
                },
            )
            db.commit()
        finally:
            db.close()
    except Exception:
        logger.warning("Failed to write error log to DB", exc_info=True)


def log_pipeline_error(
    endpoint: str,
    error: Exception,
    request_id: str | None = None,
    pipeline_stage: str | None = None,
):
    """Log a pipeline processing error to the error_logs table.

    Called directly from pipeline code (not middleware) for stage-level errors.
    """
    _log_error_to_db(
        service="worker",
        endpoint=endpoint,
        method="POST",
        status_code=500,
        error_type=type(error).__qualname__,
        message=str(error),
        traceback_str=tb.format_exc(),
        request_id=request_id or str(uuid.uuid4()),
        pipeline_stage=pipeline_stage,
    )


def register_error_handlers(app, *, service: str = "worker"):
    """Register exception handlers on the Worker FastAPI app."""

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        _log_error_to_db(
            service=service,
            endpoint=request.url.path,
            method=request.method,
            status_code=500,
            error_type=type(exc).__qualname__,
            message=str(exc),
            traceback_str=tb.format_exc(),
            request_id=request_id,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error"},
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        if exc.status_code >= 500:
            request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
            _log_error_to_db(
                service=service,
                endpoint=request.url.path,
                method=request.method,
                status_code=exc.status_code,
                error_type=type(exc).__qualname__,
                message=str(exc.detail),
                traceback_str=tb.format_exc(),
                request_id=request_id,
            )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
        )
