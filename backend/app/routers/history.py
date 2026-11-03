import threading
import time
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import facebook_api
from app.db.database import get_db
from app.models.models import PublishedPost, User
from app.routers.auth import get_current_db_user
from app.routers.facebook import token_for_post
from app.routers.schedule import live_notices, refresh_scheduled, send_notices

router = APIRouter()


@router.get("/posts")
def published_posts(
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    # Scheduled posts that have gone live since the last visit are recorded first.
    live = refresh_scheduled(db, user.id)
    send_notices(live_notices(db, user.id, live))

    total = (
        db.query(func.count(PublishedPost.id))
        .filter(PublishedPost.user_id == user.id)
        .scalar()
    )

    rows = (
        db.query(PublishedPost)
        .filter(PublishedPost.user_id == user.id)
        .order_by(PublishedPost.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )

    return {
        "success": True,
        "total": total or 0,
        "posts": [
            {
                "id": str(row.id),
                "source": row.source,
                "message": row.message,
                "with_image": row.with_image,
                "created_at": row.created_at.isoformat() + "Z",
            }
            for row in rows
        ],
    }


# ---------------------------------------------------------------- how the posts performed

INSIGHT_POSTS = 10
INSIGHT_TTL = 10 * 60

_insight_lock = threading.Lock()
_insight_cache: dict[str, tuple[float, dict, tuple]] = {}


def clear_insights_cache() -> None:
    with _insight_lock:
        _insight_cache.clear()


def _preview(text: str, length: int = 110) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= length else text[:length].rstrip() + "..."


@router.get("/insights")
def post_insights(
    refresh: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    """Engagement (reactions + comments + shares) of the latest published posts, from Facebook.

    Facebook is asked about at most 10 posts, in parallel, and the answer is kept for 10 minutes
    so opening the page again does not spend Facebook requests. A post Facebook cannot answer
    for has engagement null.
    """

    key = str(user.id)
    now = time.monotonic()

    rows = (
        db.query(PublishedPost)
        .filter(PublishedPost.user_id == user.id, PublishedPost.facebook_post_id.isnot(None))
        .order_by(PublishedPost.created_at.desc())
        .limit(INSIGHT_POSTS)
        .all()
    )
    # A new post changes this, so the saved answer is never shown for an older list of posts.
    signature = tuple(str(row.id) for row in rows)

    with _insight_lock:
        cached = _insight_cache.get(key)

    if cached and not refresh and cached[2] == signature and now - cached[0] < INSIGHT_TTL:
        return cached[1]

    jobs = [
        (str(row.id), row.facebook_post_id, token_for_post(db, user.id, row.facebook_post_id))
        for row in rows
    ]

    def look_up(job):
        _id, post_id, token = job
        return facebook_api.get_post_engagement(post_id, token) if token else None

    with ThreadPoolExecutor(max_workers=5) as pool:
        scores = list(pool.map(look_up, jobs))

    posts = [
        {
            "id": str(row.id),
            "message": _preview(row.message),
            "with_image": row.with_image,
            "created_at": row.created_at.isoformat() + "Z",
            "engagement": score,
        }
        for row, score in zip(rows, scores)
    ]

    known = [post["engagement"] for post in posts if post["engagement"] is not None]
    best = max((p for p in posts if p["engagement"] is not None), key=lambda p: p["engagement"], default=None)

    result = {
        "success": True,
        "posts": posts,
        "measured": len(known),
        "total": sum(known),
        "average": round(sum(known) / len(known), 1) if known else 0,
        "best_id": best["id"] if best and best["engagement"] > 0 else None,
    }

    with _insight_lock:
        _insight_cache[key] = (now, result, signature)

    return result
