from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.errors import ApiError
from app.core.openai_client import transcribe_audio
from app.db.database import get_db
from app.models.models import User
from app.routers.auth import get_current_db_user
from app.routers.memory import get_memory_text

router = APIRouter()

MAX_AUDIO_SIZE = 10 * 1024 * 1024  # about 10 minutes of compressed speech; the app stops at 1 minute
MIN_AUDIO_SIZE = 1000  # shorter than this is a click, not speech
EXTENSIONS = {"webm": "webm", "ogg": "ogg", "mp4": "mp4", "mpeg": "mp3", "mp3": "mp3", "wav": "wav", "x-wav": "wav", "m4a": "m4a", "x-m4a": "m4a", "aac": "m4a"}


@router.post("/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    """Turns what the user said into text for the chat box or the Autopilot topic."""

    ratelimit.check(user.id, "voice")

    content_type = (audio.content_type or "").split(";")[0].strip().lower()
    kind = content_type.split("/")[-1]

    if not content_type.startswith("audio/") or kind not in EXTENSIONS:
        raise ApiError(400, "VOICE_BAD_FORMAT", "This recording format is not supported. Please try again in Chrome, Edge or Firefox.")

    data = await audio.read()

    if len(data) > MAX_AUDIO_SIZE:
        raise ApiError(413, "VOICE_TOO_LONG", "The recording is too long. Please keep it under a minute.")

    if len(data) < MIN_AUDIO_SIZE:
        raise ApiError(400, "VOICE_TOO_SHORT", "The recording was too short. Hold the mic a little longer while you speak.")

    text = transcribe_audio(data, f"voice.{EXTENSIONS[kind]}", content_type, get_memory_text(db, user.id))

    if not text:
        raise ApiError(422, "VOICE_NOT_UNDERSTOOD", "I could not hear any words. Please try again a little closer to the microphone.")

    return {"success": True, "text": text}
