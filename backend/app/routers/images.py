from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.openai_client import generate_image_png
from app.db.database import get_db
from app.models.models import User
from app.routers.auth import get_current_db_user
from app.routers.memory import get_memory_text

router = APIRouter()


class ImageRequest(BaseModel):
    prompt: str = Field(min_length=3, max_length=1000)


@router.post("/generate")
def generate_image(
    data: ImageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    """Generate one high quality marketing image with the OpenAI image API."""

    ratelimit.check(user.id, "image")

    return Response(
        content=generate_image_png(data.prompt, get_memory_text(db, user.id)),
        media_type="image/png",
    )
