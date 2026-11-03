"""The owner's view of post emails: on/off switch, a test email, and what happened to each one."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import mailer, notify
from app.core.config import settings
from app.core.errors import ApiError
from app.core.otp import mask_email
from app.db.database import get_db
from app.models.models import NotificationLog, User, UserPreference
from app.routers.auth import get_current_db_user
from app.routers.facebook import get_user_connection

router = APIRouter()

TEST_COOLDOWN = timedelta(seconds=30)

# Why an email was not sent, in words for the owner.
REASONS = {
    "NO_EMAIL": "Your account has no email address.",
    "DISABLED_BY_ADMIN": "Post emails are switched off on this server.",
    "TURNED_OFF": "You turned post emails off.",
    "NOT_CONFIGURED": "The server has no email account set up.",
    "EMAIL_AUTH_FAILED": "The email server refused our login. The site administrator must check the email settings.",
    "EMAIL_RECIPIENT_REJECTED": "Your email provider refused the address.",
    "EMAIL_RATE_LIMITED": "The email server is limiting how many emails we send. Try again later.",
    "EMAIL_TIMEOUT": "The email server took too long to answer.",
    "EMAIL_UNAVAILABLE": "We could not reach the email server.",
    "EMAIL_FAILED": "The email server did not accept the message.",
}


class SettingsRequest(BaseModel):
    email_enabled: bool


def _enabled(db: Session, user: User) -> bool:
    row = db.get(UserPreference, user.id)
    return True if row is None else bool(row.email_notifications)


def _item(row: NotificationLog) -> dict:
    return {
        "id": row.id,
        "event": row.event,
        "status": row.status,
        "reason": REASONS.get(row.detail, "") if row.status != "sent" else "",
        "preview": row.preview,
        "created_at": row.created_at.isoformat() + "Z",
    }


@router.get("")
def notification_overview(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    rows = (
        db.query(NotificationLog)
        .filter(NotificationLog.user_id == user.id)
        .order_by(NotificationLog.created_at.desc(), NotificationLog.id.desc())
        .limit(30)
        .all()
    )

    return {
        "success": True,
        "email_enabled": _enabled(db, user),
        "server_ready": settings.POST_NOTIFICATIONS and mailer.email_configured(),
        "address": mask_email(user.email) if user.email else "",
        "items": [_item(row) for row in rows],
    }


@router.put("/settings")
def save_settings(
    data: SettingsRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    row = db.get(UserPreference, user.id)

    if row is None:
        row = UserPreference(user_id=user.id, email_notifications=data.email_enabled)
        db.add(row)
    else:
        row.email_notifications = data.email_enabled

    db.commit()

    return {"success": True, "email_enabled": data.email_enabled}


@router.post("/test")
def send_test_email(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    """Sends a sample post email right now and says exactly what happened."""

    if not user.email:
        raise ApiError(400, "NO_EMAIL", REASONS["NO_EMAIL"])

    if not mailer.email_configured():
        notify.record(user.id, "test", "failed", "NOT_CONFIGURED")
        raise ApiError(503, "EMAIL_NOT_CONFIGURED", REASONS["NOT_CONFIGURED"])

    recent = (
        db.query(NotificationLog)
        .filter(
            NotificationLog.user_id == user.id,
            NotificationLog.event == "test",
            NotificationLog.created_at > datetime.utcnow() - TEST_COOLDOWN,
        )
        .first()
    )

    if recent:
        raise ApiError(429, "TEST_COOLDOWN", "A test email was just sent. Please wait half a minute before sending another.")

    row, _token = get_user_connection(db, user.id)
    page_name = getattr(row, "page_name", None) or settings.SMTP_FROM_NAME or "Marketing AI"

    try:
        mailer.send_message(
            notify.build_post_email(
                user.email,
                "test",
                page_name,
                "Your next published, scheduled or edited post will arrive in this inbox.",
            )
        )
    except ApiError as error:
        notify.record(user.id, "test", "failed", error.code)
        raise ApiError(error.status_code, error.code, REASONS.get(error.code, error.message)) from None

    notify.record(user.id, "test", "sent")

    return {"success": True, "sent_to": mask_email(user.email)}
