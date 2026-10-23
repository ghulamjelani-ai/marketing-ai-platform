import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import facebook_api
from app.core.facebook_api import FacebookError
from app.core.openai_client import draft_week_plan, suggest_post_times
from app.db.database import get_db
from app.models.models import PublishedPost, ScheduledPost, User
from app.routers.auth import get_current_db_user
from app.routers.facebook import get_user_connection, raise_http, require_connection
from app.routers.memory import get_memory_text

router = APIRouter()

# Facebook accepts scheduled posts from 10 minutes up to 30 days ahead.
MIN_AHEAD = timedelta(minutes=15)
MAX_AHEAD = timedelta(days=29)
MAX_IMAGE_SIZE = 15 * 1024 * 1024


class DraftRequest(BaseModel):
    description: str = Field(default="", max_length=2000)
    days: int = Field(default=7, ge=1, le=7)


def _iso(moment: datetime) -> str:
    return moment.isoformat() + "Z"


def _serialize(item: ScheduledPost) -> dict:
    return {
        "id": str(item.id),
        "message": item.message,
        "with_image": item.with_image,
        "run_at": _iso(item.run_at),
        "status": item.status,
    }


def parse_run_at(value: str) -> datetime:
    try:
        moment = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="The publish time is not valid")

    if moment.tzinfo is None:
        raise HTTPException(status_code=400, detail="The publish time must include its time zone")

    utc = moment.astimezone(timezone.utc).replace(tzinfo=None)
    now = datetime.utcnow()

    if utc < now + MIN_AHEAD:
        raise HTTPException(
            status_code=400,
            detail="Choose a publish time at least 15 minutes from now",
        )

    if utc > now + MAX_AHEAD:
        raise HTTPException(
            status_code=400,
            detail="Facebook can schedule posts at most 30 days ahead",
        )

    return utc


def refresh_scheduled(db: Session, user_id: uuid.UUID) -> None:
    """Checks with Facebook which scheduled posts have gone live and records them as published."""

    row, token = get_user_connection(db, user_id)

    if not row or not token:
        return

    now = datetime.utcnow()

    due = (
        db.query(ScheduledPost)
        .filter(
            ScheduledPost.user_id == user_id,
            ScheduledPost.status == "scheduled",
            ScheduledPost.run_at <= now - timedelta(minutes=2),
        )
        .order_by(ScheduledPost.run_at)
        .limit(20)
        .with_for_update(skip_locked=True)
        .all()
    )

    for item in due:
        published = (
            facebook_api.is_post_published(item.facebook_post_id, token)
            if item.facebook_post_id
            else None
        )

        if published is True:
            item.status = "published"

            if not item.recorded:
                db.add(
                    PublishedPost(
                        user_id=user_id,
                        source="scheduled",
                        message=item.message,
                        with_image=item.with_image,
                        facebook_post_id=item.facebook_post_id,
                        created_at=item.run_at,
                    )
                )
                item.recorded = True
        elif published is None and item.run_at < now - timedelta(days=2):
            # Facebook no longer knows this post (for example it was deleted on Facebook).
            item.status = "removed"

    db.commit()


@router.post("/draft")
def draft_plan(
    data: DraftRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    memory = get_memory_text(db, user.id)

    if not data.description.strip() and not memory.strip():
        raise HTTPException(
            status_code=400,
            detail="Tell me about your business first: what it sells, where, and your goal.",
        )

    return {
        "success": True,
        "posts": draft_week_plan(data.description, memory, data.days),
    }


@router.post("/post")
async def schedule_post(
    message: str = Form(""),
    run_at: str = Form(...),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    row, token = require_connection(db, user)

    when = parse_run_at(run_at)
    text = message.strip()

    image_bytes = None

    if image is not None:
        if not image.content_type or not image.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="Please upload a valid image file")

        image_bytes = await image.read()

        if not image_bytes:
            raise HTTPException(status_code=400, detail="Uploaded image is empty")

        if len(image_bytes) > MAX_IMAGE_SIZE:
            raise HTTPException(status_code=400, detail="Image is too large. Maximum size is 15 MB.")

    if not text and not image_bytes:
        raise HTTPException(status_code=400, detail="A scheduled post needs text or a picture")

    try:
        if image_bytes:
            result = facebook_api.publish_photo(
                row.page_id,
                token,
                image_bytes,
                image.filename or "facebook-image.png",
                image.content_type,
                text,
                scheduled_at=when,
            )
            facebook_post_id = result.get("post_id") or result.get("id")
        else:
            result = facebook_api.publish_text(
                row.page_id,
                token,
                text,
                scheduled_at=when,
            )
            facebook_post_id = result.get("id")
    except FacebookError as error:
        raise_http(error)

    item = ScheduledPost(
        user_id=user.id,
        message=text,
        with_image=bool(image_bytes),
        run_at=when,
        status="scheduled",
        facebook_post_id=facebook_post_id,
    )

    db.add(item)
    db.commit()
    db.refresh(item)

    return {"success": True, "post": _serialize(item)}


@router.get("")
def list_scheduled(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    refresh_scheduled(db, user.id)

    upcoming = (
        db.query(ScheduledPost)
        .filter(ScheduledPost.user_id == user.id, ScheduledPost.status == "scheduled")
        .order_by(ScheduledPost.run_at)
        .all()
    )

    past = (
        db.query(ScheduledPost)
        .filter(ScheduledPost.user_id == user.id, ScheduledPost.status != "scheduled")
        .order_by(ScheduledPost.run_at.desc())
        .limit(20)
        .all()
    )

    return {
        "success": True,
        "upcoming": [_serialize(item) for item in upcoming],
        "past": [_serialize(item) for item in past],
    }


def _cancel(db: Session, user: User, item: ScheduledPost) -> None:
    row, token = get_user_connection(db, user.id)

    if item.facebook_post_id and row and token:
        try:
            facebook_api.delete_post(item.facebook_post_id, token)
        except FacebookError as error:
            raise_http(error)

    item.status = "cancelled"


@router.delete("/{post_id}")
def cancel_scheduled(
    post_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    item = (
        db.query(ScheduledPost)
        .filter(
            ScheduledPost.id == post_id,
            ScheduledPost.user_id == user.id,
            ScheduledPost.status == "scheduled",
        )
        .first()
    )

    if not item:
        raise HTTPException(status_code=404, detail="Scheduled post not found")

    _cancel(db, user, item)
    db.commit()

    return {"success": True}


@router.post("/cancel-all")
def cancel_all(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    items = (
        db.query(ScheduledPost)
        .filter(ScheduledPost.user_id == user.id, ScheduledPost.status == "scheduled")
        .all()
    )

    cancelled = 0
    failed = 0

    for item in items:
        try:
            _cancel(db, user, item)
            cancelled += 1
        except HTTPException:
            failed += 1

    db.commit()

    return {"success": True, "cancelled": cancelled, "failed": failed}


# ---------------------------------------------------------------------------
# Best time to post
# ---------------------------------------------------------------------------

MIN_POSTS_FOR_OWN_DATA = 10
WINDOWS = [(6, 10), (10, 14), (14, 18), (18, 22)]

DEFAULT_TIMES = [
    {"time": "09:00", "reason": "Many people check Facebook in the morning before work or school."},
    {"time": "13:00", "reason": "Lunch breaks are a common time to scroll through Facebook."},
    {"time": "19:00", "reason": "In the evening many people relax and browse."},
]


def best_time_from_own_posts(db: Session, user: User, tz_offset: int):
    """Uses how the user's own published posts performed, grouped by time of day."""

    row, token = get_user_connection(db, user.id)

    if not row or not token:
        return None

    posts = (
        db.query(PublishedPost)
        .filter(PublishedPost.user_id == user.id, PublishedPost.facebook_post_id.isnot(None))
        .order_by(PublishedPost.created_at.desc())
        .limit(25)
        .all()
    )

    samples = []

    for post in posts:
        engagement = facebook_api.get_post_engagement(post.facebook_post_id, token)

        if engagement is not None:
            # tz_offset is the browser value (minutes UTC minus local time)
            local = post.created_at - timedelta(minutes=tz_offset)
            samples.append((local.hour, engagement))

    if len(samples) < MIN_POSTS_FOR_OWN_DATA:
        return None

    ranked = []

    for start, end in WINDOWS:
        values = [engagement for hour, engagement in samples if start <= hour < end]

        # a window needs at least 2 posts, otherwise one lucky post decides
        if len(values) >= 2:
            ranked.append((sum(values) / len(values), start, end, len(values)))

    ranked.sort(reverse=True)
    ranked = [item for item in ranked if item[0] > 0][:2]

    if not ranked:
        return None

    return {
        "source": "your_posts",
        "based_on": len(samples),
        "note": (
            f"Based on how your last {len(samples)} posts performed. "
            "With few posts this is only a rough guide."
        ),
        "times": [
            {
                "time": f"{(start + end) // 2:02d}:00",
                "reason": (
                    f"Your posts published between {start:02d}:00 and {end:02d}:00 "
                    f"got {mean:.1f} reactions, comments and shares on average ({count} posts)."
                ),
            }
            for mean, start, end, count in ranked
        ],
    }


@router.get("/best-time")
def best_time(
    tz_offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    tz_offset = max(-840, min(840, tz_offset))

    own = best_time_from_own_posts(db, user, tz_offset)

    if own:
        return {"success": True, **own}

    try:
        times = suggest_post_times(get_memory_text(db, user.id))
    except HTTPException:
        times = DEFAULT_TIMES

    return {
        "success": True,
        "source": "general",
        "based_on": 0,
        "note": (
            "These are general starting points based on typical customer routines, "
            "not measured from your Page. After about 10 posts the app will use how "
            "your own posts performed."
        ),
        "times": times,
    }

