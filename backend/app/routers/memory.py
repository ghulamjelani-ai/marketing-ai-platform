import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.openai_client import update_memory_summary
from app.db.database import SessionLocal, get_db
from app.models.models import User, UserMemory
from app.routers.auth import get_current_db_user

router = APIRouter()


class MemoryUpdate(BaseModel):
    summary: str = Field(default="", max_length=2000)


def get_memory_text(db: Session, user_id: uuid.UUID) -> str:
    row = db.query(UserMemory).filter(UserMemory.user_id == user_id).first()

    return row.summary if row and row.summary else ""


def save_memory(db: Session, user_id: uuid.UUID, summary: str) -> UserMemory:
    row = db.query(UserMemory).filter(UserMemory.user_id == user_id).first()

    if row is None:
        row = UserMemory(user_id=user_id, summary=summary)
        db.add(row)
    else:
        row.summary = summary

    db.commit()
    db.refresh(row)

    return row


def update_memory_in_background(user_id: uuid.UUID, user_message: str) -> None:
    """Runs after the chat reply was sent. Failures here must never affect the chat."""

    db = SessionLocal()

    try:
        current = get_memory_text(db, user_id)
        updated = update_memory_summary(current, user_message)

        # An empty answer never erases an existing profile.
        if updated and updated != current:
            save_memory(db, user_id, updated)
    except Exception as exc:
        print("Memory update skipped:", repr(exc))
    finally:
        db.close()


def _serialize(row: UserMemory | None) -> dict:
    return {
        "success": True,
        "summary": row.summary if row else "",
        "updated_at": row.updated_at.isoformat() + "Z" if row and row.updated_at else None,
    }


@router.get("")
def read_memory(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    row = db.query(UserMemory).filter(UserMemory.user_id == user.id).first()

    return _serialize(row)


@router.put("")
def write_memory(
    data: MemoryUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    return _serialize(save_memory(db, user.id, data.summary.strip()))


@router.delete("")
def clear_memory(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    db.query(UserMemory).filter(UserMemory.user_id == user.id).delete()
    db.commit()

    return _serialize(None)
