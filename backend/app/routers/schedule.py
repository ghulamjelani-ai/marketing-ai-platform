import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import facebook_api, notify, ratelimit
from app.core.errors import ApiError
from app.core.facebook_api import FacebookError
from app.core.openai_client import draft_week_plan, suggest_post_times
from app.db.database import SessionLocal, get_db
from app.models.models import PublishedPost, ScheduledPost, User
from app.routers.auth import get_current_db_user
from app.routers.facebook import get_user_connection, raise_http, require_connection, token_for_post
from app.routers.memory import get_memory_text

router = APIRouter()

# Facebook accepts scheduled posts from 10 minutes up to 30 days ahead.
MIN_AHEAD = timedelta(minutes=15)
MAX_AHEAD = timedelta(days=29)
MAX_IMAGE_SIZE = 15 * 1024 * 1024
# Facebook does not accept changes to a post that is about to go out.
EDIT_LOCK = timedelta(minutes=10)


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


def refresh_scheduled(db: Session, user_id: uuid.UUID) -> list[dict]:
    """Checks with Facebook which scheduled posts have gone live and records them as published.

    Returns the posts that went live in this call, so the owner can be told about them once.
    """

    row, token = get_user_connection(db, user_id)

    if not row or not token:
        return []

    live: list[dict] = []

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
            facebook_api.is_post_published(item.facebook_post_id, token_for_post(db, user_id, item.facebook_post_id))
            if item.facebook_post_id
            else None
        )

        if published is True:
            item.status = "published"
            live.append(
                {
                    "text": item.message,
                    "with_image": item.with_image,
                    "post_id": item.facebook_post_id,
                    "when": item.run_at,
                }
            )

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

    return live


def live_notices(db: Session, user_id: uuid.UUID, live: list[dict]) -> list[dict]:
    """The emails to send for posts that just went live (built now, sent after the reply)."""

    if not live:
        return []

    user = db.get(User, user_id)
    row, _token = get_user_connection(db, user_id)

    if not user or not user.email:
        return []

    return [
        {"to": user.email, "user_id": user.id, "event": "live", "page_name": getattr(row, "page_name", None), **item}
        for item in live
    ]


def send_notices(notices: list[dict]) -> None:
    for notice in notices:
        notify.submit(
            notice["to"],
            notice["event"],
            user_id=notice.get("user_id"),
            page_name=notice.get("page_name"),
            text=notice.get("text", ""),
            when=notice.get("when"),
            post_id=notice.get("post_id"),
            with_image=notice.get("with_image", False),
        )


def poll_due_posts() -> int:
    """Marks due scheduled posts as live for every user and emails the owners.

    Runs from the background poller, so owners hear about a post even when the site is closed.
    Returns how many posts went live.
    """

    went_live = 0

    with SessionLocal() as db:
        user_ids = [
            row[0]
            for row in db.query(ScheduledPost.user_id)
            .filter(
                ScheduledPost.status == "scheduled",
                ScheduledPost.run_at <= datetime.utcnow() - timedelta(minutes=2),
            )
            .distinct()
            .all()
        ]

        for user_id in user_ids:
            try:
                live = refresh_scheduled(db, user_id)
                went_live += len(live)
                send_notices(live_notices(db, user_id, live))
            except Exception as exc:  # noqa: BLE001 - one user's problem must not stop the others
                db.rollback()
                print(f"Scheduled post check failed: {type(exc).__name__}")

    return went_live


@router.post("/draft")
def draft_plan(
    data: DraftRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    ratelimit.check(user.id, "draft")

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


async def read_image(image: UploadFile | None) -> bytes | None:
    """The bytes of an uploaded picture, or None when there is none. Refuses bad uploads."""

    if image is None:
        return None

    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload a valid image file")

    data = await image.read()

    if not data:
        raise HTTPException(status_code=400, detail="Uploaded image is empty")

    if len(data) > MAX_IMAGE_SIZE:
        raise HTTPException(status_code=400, detail="Image is too large. Maximum size is 15 MB.")

    return data


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

    image_bytes = await read_image(image)

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

    notify.submit(
        user.email,
        "scheduled",
        user_id=user.id,
        page_name=getattr(row, "page_name", None),
        text=text,
        when=when,
        post_id=facebook_post_id,
        with_image=bool(image_bytes),
    )

    return {"success": True, "post": _serialize(item)}


@router.get("")
def list_scheduled(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    live = refresh_scheduled(db, user.id)
    send_notices(live_notices(db, user.id, live))

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


@router.put("/{post_id}")
async def edit_scheduled(
    post_id: uuid.UUID,
    message: str | None = Form(None),
    run_at: str | None = Form(None),
    remove_image: bool = Form(False),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    """Changes a post that is still waiting: its text, publish time and/or picture.

    A text post is replaced by a new scheduled post and the old one is deleted. A photo post
    whose picture stays the same is updated in place. A new or removed picture replaces the
    post. The old post is deleted only after the new one exists, so a failure never leaves
    the owner with nothing scheduled.
    """

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
        raise ApiError(404, "POST_NOT_FOUND", "That scheduled post was not found. It may already be live or removed.")

    if item.run_at < datetime.utcnow() + EDIT_LOCK:
        raise ApiError(
            409,
            "POST_TOO_CLOSE",
            "This post goes out in less than 10 minutes, so it can no longer be changed.",
        )

    text = message.strip() if message is not None else item.message
    when = parse_run_at(run_at) if run_at else None
    image_bytes = await read_image(image)

    new_picture = image_bytes is not None
    dropping_picture = bool(remove_image) and item.with_image and not new_picture
    with_image = new_picture or (item.with_image and not dropping_picture)

    if not text and not with_image:
        raise ApiError(400, "POST_EMPTY", "A post needs text or a picture.")

    if text == item.message and when is None and not new_picture and not dropping_picture:
        return {"success": True, "post": _serialize(item), "changed": False}

    old_id = item.facebook_post_id
    token = token_for_post(db, user.id, old_id)

    if not old_id or not token:
        raise ApiError(
            409,
            "FB_NOT_CONNECTED",
            "This post's Facebook Page is not connected any more. Reconnect it and try again.",
        )

    new_when = when or item.run_at
    new_id = old_id

    try:
        if item.with_image and not new_picture and not dropping_picture:
            facebook_api.update_post(
                old_id,
                token,
                message=text if text != item.message else None,
                scheduled_at=when,
            )
        else:
            page_id = old_id.split("_")[0]

            if new_picture:
                created = facebook_api.publish_photo(
                    page_id,
                    token,
                    image_bytes,
                    image.filename or "facebook-image.png",
                    image.content_type,
                    text,
                    scheduled_at=new_when,
                )
                new_id = created.get("post_id") or created.get("id")
            else:
                created = facebook_api.publish_text(page_id, token, text, scheduled_at=new_when)
                new_id = created.get("id")

            try:
                facebook_api.delete_post(old_id, token)
            except FacebookError:
                # Keep exactly one copy: take the new post back and report the problem.
                try:
                    facebook_api.delete_post(new_id, token)
                except FacebookError:
                    pass

                raise
    except FacebookError as error:
        raise_http(error)

    item.message = text
    item.with_image = with_image
    item.run_at = new_when
    item.facebook_post_id = new_id
    db.commit()
    db.refresh(item)

    row, _ = get_user_connection(db, user.id)
    notify.submit(
        user.email,
        "updated",
        user_id=user.id,
        page_name=getattr(row, "page_name", None),
        text=text,
        when=new_when,
        post_id=new_id,
        with_image=with_image,
    )

    return {"success": True, "post": _serialize(item), "changed": True}


def _cancel(db: Session, user: User, item: ScheduledPost) -> None:
    row, token = get_user_connection(db, user.id)

    if item.facebook_post_id and row and token:
        try:
            facebook_api.delete_post(item.facebook_post_id, token_for_post(db, user.id, item.facebook_post_id))
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
        except (HTTPException, ApiError):
            failed += 1

    db.commit()

    return {"success": True, "cancelled": cancelled, "failed": failed}


# Finished entries (published, cancelled or removed) can be cleared from the list.
# Facebook is not contacted: those posts are no longer waiting there, and published
# posts keep their own record in the History (PublishedPost).


@router.delete("/earlier/{post_id}")
def clear_earlier(
    post_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    item = (
        db.query(ScheduledPost)
        .filter(ScheduledPost.id == post_id, ScheduledPost.user_id == user.id)
        .first()
    )

    if not item:
        raise ApiError(404, "POST_NOT_FOUND", "That post is not in your list any more.")

    if item.status == "scheduled":
        raise ApiError(
            409,
            "POST_STILL_SCHEDULED",
            "This post is still waiting to go out. Use Remove to cancel it first.",
        )

    db.delete(item)
    db.commit()

    return {"success": True}


@router.post("/clear-earlier")
def clear_all_earlier(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    cleared = (
        db.query(ScheduledPost)
        .filter(ScheduledPost.user_id == user.id, ScheduledPost.status != "scheduled")
        .delete(synchronize_session=False)
    )
    db.commit()

    return {"success": True, "cleared": cleared}


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
        .filter(
            PublishedPost.user_id == user.id,
            # Only posts on the Page chosen now (post ids start with "PAGEID_").
            PublishedPost.facebook_post_id.like(f"{row.page_id}\\_%", escape="\\"),
        )
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
    except (HTTPException, ApiError):
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

