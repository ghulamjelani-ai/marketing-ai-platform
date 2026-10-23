from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.openai_client import draft_single_post
from app.db.database import get_db
from app.models.models import User
from app.routers.auth import get_current_db_user
from app.routers.memory import get_memory_text, update_memory_in_background

router = APIRouter()


class AutopilotRequest(BaseModel):
    request: str = Field(default="", max_length=2000)


@router.post("/post")
def autopilot_post(
    data: AutopilotRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    """Writes one ready-to-publish post (caption, description, hashtags, image prompt)."""

    memory = get_memory_text(db, user.id)

    if not data.request.strip() and not memory.strip():
        raise HTTPException(
            status_code=400,
            detail="Tell me what the post is about, or describe your business in the chat first.",
        )

    post = draft_single_post(data.request, memory)

    if data.request.strip():
        background_tasks.add_task(update_memory_in_background, user.id, data.request)

    return {"success": True, "post": post}
