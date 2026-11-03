from fastapi import APIRouter, BackgroundTasks, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.openai_client import check_topic_intent, draft_single_post
from app.core.topic_check import EXAMPLE, TopicError, validate_topic
from app.db.database import get_db
from app.models.models import User
from app.routers.auth import get_current_db_user
from app.routers.memory import get_memory_text, update_memory_in_background

router = APIRouter()


class AutopilotRequest(BaseModel):
    # Longer text is still accepted here so validate_topic can answer with a clear message.
    request: str = Field(default="", max_length=10000)


@router.post("/post")
def autopilot_post(
    data: AutopilotRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    """Writes one ready-to-publish post (caption, description, hashtags, image prompt).

    Garbage topics never reach the post writer: the rules in topic_check run first,
    then a cheap AI intent check. Either one failing stops the request with HTTP 400.
    """

    ratelimit.check(user.id, "autopilot")

    topic = validate_topic(data.request)

    intent = check_topic_intent(topic)

    if not intent["valid"]:
        reason = intent["reason"] or "The topic does not describe something to post about."
        raise TopicError("TOPIC_UNCLEAR", reason.rstrip(".") + ". " + EXAMPLE)

    memory = get_memory_text(db, user.id)
    post = draft_single_post(topic, memory)

    background_tasks.add_task(update_memory_in_background, user.id, topic)

    return {"success": True, "post": post}
