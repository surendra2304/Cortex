from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
import uuid
import contextvars

# Global context var for distributed tracing across services
trace_id_ctx = contextvars.ContextVar("trace_id_ctx", default=None)


class TracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        trace_id = request.headers.get("X-Trace-ID") or f"trc_{uuid.uuid4().hex[:12]}"
        token = trace_id_ctx.set(trace_id)
        try:
            response = await call_next(request)
            response.headers["X-Trace-ID"] = trace_id
            return response
        finally:
            trace_id_ctx.reset(token)


def get_current_trace_id() -> str:
    tid = trace_id_ctx.get()
    return tid or f"trc_{uuid.uuid4().hex[:12]}"
