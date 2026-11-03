"""Background check for scheduled posts that have gone live.

Facebook publishes scheduled posts by itself. This loop only notices it: every
POLL_SECONDS it asks Facebook about posts that are due, records them as published and
emails the owner. It runs inside the single backend process (see settings.BACKGROUND_POLLER).
"""

import asyncio

from app.core.config import settings

FIRST_DELAY_SECONDS = 30


async def run() -> None:
    # Imported here: the router module imports half the application.
    from app.routers.schedule import poll_due_posts

    await asyncio.sleep(FIRST_DELAY_SECONDS)

    while True:
        try:
            await asyncio.to_thread(poll_due_posts)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            print(f"Background post check failed: {type(exc).__name__}")

        await asyncio.sleep(settings.POLL_SECONDS)
