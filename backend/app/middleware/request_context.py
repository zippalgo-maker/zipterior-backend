from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from threading import Lock
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from app.core.config import settings


logger = logging.getLogger("zipterior.request")


class RequestContextMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._rate_lock = Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def _client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
        if request.client:
            return request.client.host
        return "unknown"

    def _rate_limited(self, client_ip: str) -> bool:
        if not settings.rate_limit_enabled:
            return False
        now = time.monotonic()
        cutoff = now - 60.0
        limit = settings.rate_limit_requests_per_minute
        with self._rate_lock:
            hits = self._hits[client_ip]
            while hits and hits[0] < cutoff:
                hits.popleft()
            if len(hits) >= limit:
                return True
            hits.append(now)
        return False

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = (
            request.headers.get(settings.request_id_header)
            or str(uuid4())
        )[:100]
        client_ip = self._client_ip(request)
        request.state.request_id = request_id
        started = time.perf_counter()

        if self._rate_limited(client_ip):
            response = JSONResponse(
                status_code=429,
                content={"detail": "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."},
            )
            response.headers[settings.request_id_header] = request_id
            return response

        try:
            response = await call_next(request)
        except Exception:
            duration_ms = round((time.perf_counter() - started) * 1000, 2)
            logger.exception(
                "unhandled request exception",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
            )
            raise

        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers[settings.request_id_header] = request_id

        if settings.request_log_enabled:
            level = (
                logging.WARNING
                if response.status_code >= 500
                or duration_ms >= settings.slow_request_ms
                else logging.INFO
            )
            logger.log(
                level,
                "request completed",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                    "duration_ms": duration_ms,
                    "client_ip": client_ip,
                },
            )

        return response
