"""Exception handler middleware that logs errors to the error_logs table.

Additive — does not replace or interfere with existing logging.
Catches unhandled exceptions, logs them to DB, then re-raises.
"""

import logging
import traceback as tb
import uuid

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy import text

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


async def error_logging_middleware(request: Request, call_next, *, service: str = "api"):
    """Middleware that catches unhandled exceptions and logs them to DB."""
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    try:
        response = await call_next(request)
        return response
    except Exception as exc:
        error_type = type(exc).__qualname__
        message = str(exc)
        traceback_str = tb.format_exc()
        endpoint = request.url.path
        method = request.method
        status_code = 500

        _log_error_to_db(
            service=service,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            error_type=error_type,
            message=message,
            traceback_str=traceback_str,
            request_id=request_id,
        )

        raise


def register_error_handlers(app, *, service: str = "api"):
    """Register exception handlers on a FastAPI app that log to error_logs.

    Handles both unhandled exceptions (500s) and HTTPExceptions (4xx/5xx).
    """
    from fastapi import HTTPException
    from starlette.exceptions import HTTPException as StarletteHTTPException

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
