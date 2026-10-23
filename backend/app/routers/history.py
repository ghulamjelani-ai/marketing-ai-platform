from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.models import PublishedPost, User
from app.routers.auth import get_current_db_user
from app.routers.schedule import refresh_scheduled

router = APIRouter()


@router.get("/posts")
def published_posts(
    limit: int = 50,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    # Scheduled posts that have gone live since the last visit are recorded first.
    refresh_scheduled(db, user.id)

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
