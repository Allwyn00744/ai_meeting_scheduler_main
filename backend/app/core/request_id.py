"""
Per-request correlation ID: generated (or forwarded, if the caller/
load balancer already set X-Request-ID) at the very start of request
handling, made available to every log line emitted while handling
that request via a contextvar (see app/core/logging_config.py), and
echoed back in the response so a client or upstream proxy can
correlate its own logs with this service's.
"""
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

_request_id_ctx_var: ContextVar[str | None] = ContextVar(
    "request_id", default=None,
)


def get_request_id() -> str | None:
    return _request_id_ctx_var.get()


class RequestIDMiddleware(BaseHTTPMiddleware):

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        token = _request_id_ctx_var.set(request_id)

        try:
            response = await call_next(request)
        finally:
            _request_id_ctx_var.reset(token)

        response.headers["X-Request-ID"] = request_id
        return response
