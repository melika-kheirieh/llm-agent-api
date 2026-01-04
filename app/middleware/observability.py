import time
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import logging

logger = logging.getLogger(__name__)



class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        status = "error"

        try:
            response = await call_next(request)
            status = response.status_code
            return response

        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "http_request",
                extra={
                    "path": request.url.path,
                    "method": request.method,
                    "status": status,
                    "latency_ms": round(duration_ms, 2),
                },
            )
