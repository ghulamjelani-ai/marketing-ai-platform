"""Stops the same publish request from reaching Facebook twice.

The browser sends an `Idempotency-Key` header (a random UUID per Autopilot run) with
publish and schedule requests. While a request with that key is running, a repeat
gets HTTP 409; after it succeeded, a repeat gets the stored answer and nothing is
sent to Facebook again. A failed request frees the key, so a retry can use it.

Keys live in memory for 15 minutes, which covers double clicks and retries. The
backend runs as a single process, so memory is enough here.
"""

import threading
import time

from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

PROTECTED_PATHS = {"/facebook/publish", "/facebook/publish-photo", "/schedule/post"}
TTL_SECONDS = 15 * 60
MAX_KEY_LENGTH = 100

_lock = threading.Lock()
_entries: dict[tuple[str, str], dict] = {}


def _purge(now: float) -> None:
    for entry_key in [k for k, v in _entries.items() if now - v["at"] > TTL_SECONDS]:
        del _entries[entry_key]


def clear() -> None:
    with _lock:
        _entries.clear()


class IdempotencyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        key = request.headers.get("idempotency-key", "").strip()

        if request.method != "POST" or request.url.path not in PROTECTED_PATHS or not key:
            return await call_next(request)

        if len(key) > MAX_KEY_LENGTH:
            return JSONResponse(
                status_code=400,
                content={"error": {"code": "BAD_IDEMPOTENCY_KEY", "message": "Idempotency-Key is too long."}},
            )

        entry_key = (request.url.path, key)
        now = time.time()

        with _lock:
            _purge(now)
            entry = _entries.get(entry_key)

            if entry is None:
                _entries[entry_key] = {"at": now, "done": False}

        if entry is not None:
            if entry["done"]:
                return Response(
                    content=entry["body"],
                    status_code=entry["status"],
                    media_type="application/json",
                    headers={"Idempotent-Replay": "true"},
                )

            return JSONResponse(
                status_code=409,
                content={"error": {"code": "ALREADY_RUNNING", "message": "This post is already being published."}},
            )

        try:
            response = await call_next(request)
        except Exception:
            with _lock:
                _entries.pop(entry_key, None)
            raise

        if not 200 <= response.status_code < 300:
            with _lock:
                _entries.pop(entry_key, None)
            return response

        body = b"".join([chunk async for chunk in response.body_iterator])

        with _lock:
            _entries[entry_key] = {"at": now, "done": True, "status": response.status_code, "body": body}

        headers = {k: v for k, v in response.headers.items() if k.lower() != "content-length"}
        return Response(content=body, status_code=response.status_code, headers=headers)
