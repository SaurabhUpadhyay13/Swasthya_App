"""One error shape for the whole API:

    {"error": {"code": "not_found", "message": "...", "details": [...]}}

Routes raise a plain HTTPException (via `api_error`); the handlers below
convert every failure - HTTP, validation, or unexpected - into that shape.
"""

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("careflow")

_DEFAULT_CODES = {404: "not_found", 405: "method_not_allowed", 409: "conflict", 422: "validation_error"}


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[dict] | None = None


class ErrorResponse(BaseModel):
    """Documented in OpenAPI so API consumers know what failures look like."""

    error: ErrorBody


def api_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _envelope(code: str, message: str, details: list[dict] | None = None) -> dict:
    error: dict = {"code": code, "message": message}
    if details:
        error["details"] = details
    return {"error": error}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc.detail, dict) and "code" in exc.detail:
            body = _envelope(exc.detail["code"], exc.detail["message"])
        else:
            code = _DEFAULT_CODES.get(exc.status_code, "http_error")
            body = _envelope(code, str(exc.detail))
        return JSONResponse(body, status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"field": ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]), "message": e["msg"]}
            for e in exc.errors()
        ]
        body = _envelope("validation_error", "Request validation failed.", details)
        return JSONResponse(body, status_code=422)

    @app.exception_handler(Exception)
    async def unexpected_error(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled error", exc_info=exc)
        return JSONResponse(_envelope("internal_error", "Something went wrong."), status_code=500)
