"""Request guards for a public deployment: request ids, safe headers, access log, clean 500s.

- every response carries `X-Request-ID` (the id is also in the log line and in 500 answers),
- standard security headers are added, and `Cache-Control: no-store` keeps private answers
  out of shared caches,
- an error nobody planned for becomes {"error": {"code": "INTERNAL_ERROR", ...}} instead of a
  bare "Internal Server Error", and the traceback is logged with the request id.

The middleware sits inside CORS, so even a 500 answer carries the CORS headers and the browser
can read it.
"""

import logging
import time
import uuid

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app.core.config import settings

logger = logging.getLogger("marketing_ai")

QUIET_PATHS = {"/health", "/ready", "/"}


def configure_logging() -> None:
    root = logging.getLogger()

    if root.handlers:
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def security_headers() -> dict[str, str]:
    headers = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Referrer-Policy": "no-referrer",
        "Cross-Origin-Resource-Policy": "same-site",
        "Permissions-Policy": "camera=(), geolocation=(), payment=()",
        "Cache-Control": "no-store",
    }

    if settings.APP_ENV == "production":
        headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

    return headers


class GuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        request_id = request.headers.get("x-request-id", "").strip()[:64] or uuid.uuid4().hex[:12]
        started = time.perf_counter()

        try:
            response = await call_next(request)
        except Exception:  # noqa: BLE001 - the last line of defence
            logger.exception("Unhandled error %s %s [%s]", request.method, request.url.path, request_id)
            response = JSONResponse(
                status_code=500,
                content={
                    "error": {
                        "code": "INTERNAL_ERROR",
                        "message": "Something went wrong on our side. Please try again in a moment.",
                        "request_id": request_id,
                    }
                },
            )

        response.headers["X-Request-ID"] = request_id

        for name, value in security_headers().items():
            response.headers.setdefault(name, value)

        if request.url.path not in QUIET_PATHS:
            logger.info(
                "%s %s -> %s in %d ms [%s]",
                request.method,
                request.url.path,
                response.status_code,
                (time.perf_counter() - started) * 1000,
                request_id,
            )

        return response
