import logging
from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

logger = logging.getLogger(__name__)

def generate_error_response(code: str, message: str, details=None, request_id=None):
    return {
        "error": {
            "code": code,
            "message": message,
            "details": details
        },
        "request_id": request_id
    }

async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.error(f"Unhandled server error [request_id={request_id}]: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=generate_error_response(
            code="INTERNAL_ERROR",
            message="An unexpected internal server error occurred.",
            request_id=request_id
        )
    )

async def value_error_handler(request: Request, exc: ValueError):
    request_id = getattr(request.state, "request_id", None)
    logger.warning(f"Domain validation error [request_id={request_id}]: {exc}")
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content=generate_error_response(
            code="VALIDATION_ERROR",
            message=str(exc),
            request_id=request_id
        )
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    request_id = getattr(request.state, "request_id", None)
    logger.warning(f"Request validation error [request_id={request_id}]: {exc}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=generate_error_response(
            code="UNPROCESSABLE_ENTITY",
            message="Request validation failed.",
            details=exc.errors(),
            request_id=request_id
        )
    )
