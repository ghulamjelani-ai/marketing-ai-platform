"""A small per-user limit on the calls that cost money (AI text, pictures, speech).

Without it one signed-in user, or a script using a stolen login, could run up the OpenAI bill.
Counts live in memory, which is enough for the single backend process this app runs as.
Limits are off when APP_ENV is "test", so the automated suites can call routes freely.
"""

import threading
import time
from collections import defaultdict, deque

from app.core.config import settings
from app.core.errors import ApiError

# name -> (calls, seconds)
LIMITS = {
    "chat": (30, 60),
    "image": (8, 60),
    "autopilot": (12, 60),
    "voice": (20, 60),
    "draft": (10, 60),
}

_lock = threading.Lock()
_hits: dict[tuple[str, str], deque] = defaultdict(deque)


def clear() -> None:
    with _lock:
        _hits.clear()


def check(user_id, name: str) -> None:
    """Raises 429 RATE_LIMITED when this user has made too many `name` calls recently."""

    if settings.APP_ENV == "test":
        return

    calls, seconds = LIMITS[name]
    now = time.monotonic()
    key = (str(user_id), name)

    with _lock:
        window = _hits[key]

        while window and now - window[0] > seconds:
            window.popleft()

        if len(window) >= calls:
            wait = int(seconds - (now - window[0])) + 1
            raise ApiError(
                429,
                "RATE_LIMITED",
                f"You are doing that too quickly. Please wait {wait} seconds and try again.",
            )

        window.append(now)
