from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core import otp, password_reset
from app.core.errors import ApiError
from app.core.firebase import verify_firebase_token
from app.db.database import get_db
from app.models.models import User

router = APIRouter()


def get_current_firebase_user(authorization: str | None = Header(default=None)):
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization header",
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header must start with Bearer",
        )

    id_token = authorization.replace("Bearer ", "").strip()

    if not id_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Firebase ID token",
        )

    return verify_firebase_token(id_token)


def get_or_create_user(db: Session, firebase_user: dict):
    firebase_uid = firebase_user.get("uid")

    if not firebase_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Firebase uid missing",
        )

    user = db.query(User).filter(User.firebase_uid == firebase_uid).first()

    if user is None:
        user = User(firebase_uid=firebase_uid)
        db.add(user)

        try:
            db.commit()
        except IntegrityError:
            # The first sign-in sends two sync calls at once; the other one created the row.
            db.rollback()
            user = db.query(User).filter(User.firebase_uid == firebase_uid).first()

            if user is None:
                raise

    # Both calls still save what their token says (for example a name set just now).
    user.name = firebase_user.get("name") or user.name
    user.email = firebase_user.get("email") or user.email
    user.photo_url = firebase_user.get("picture") or user.photo_url

    db.commit()
    db.refresh(user)

    return user


def get_current_db_user(
    firebase_user: dict = Depends(get_current_firebase_user),
    db: Session = Depends(get_db),
):
    # A Google sign-in only becomes a session after its email code was confirmed.
    if otp.needs_otp(firebase_user) and not otp.is_verified(db, firebase_user):
        raise ApiError(403, "OTP_REQUIRED", "Enter the code we emailed you to finish signing in.")

    return get_or_create_user(db, firebase_user)


class OtpVerifyRequest(BaseModel):
    code: str = Field(min_length=1, max_length=20)


class OtpSendRequest(BaseModel):
    # Only changes the wording of the email ("sign-in" or "sign-up" code).
    purpose: Literal["sign_in", "sign_up"] = "sign_in"


@router.get("/otp/status")
def login_code_status(
    firebase_user: dict = Depends(get_current_firebase_user),
    db: Session = Depends(get_db),
):
    """What the code screen shows (code sent, waits, lock), so a reload restores it."""

    return otp.status(db, firebase_user)


@router.post("/otp/send")
def send_login_code(
    request: Request,
    data: OtpSendRequest | None = None,
    firebase_user: dict = Depends(get_current_firebase_user),
    db: Session = Depends(get_db),
):
    """Emails a 6-digit code to the address in this request's verified Firebase token.

    The browser cannot choose the address: it always comes from the token.
    """

    ip = request.client.host if request.client else ""
    return otp.send_code(db, firebase_user, ip=ip, purpose=(data or OtpSendRequest()).purpose)


@router.post("/otp/verify")
def verify_login_code(
    data: OtpVerifyRequest,
    firebase_user: dict = Depends(get_current_firebase_user),
    db: Session = Depends(get_db),
):
    otp.verify_code(db, firebase_user, data.code)
    user = get_or_create_user(db, firebase_user)

    return {"success": True, "user": {"id": str(user.id), "email": user.email}}


@router.get("/me")
def me(user: User = Depends(get_current_db_user)):
    return {
        "success": True,
        "user": {
            "id": str(user.id),
            "firebase_uid": user.firebase_uid,
            "name": user.name,
            "email": user.email,
            "photo_url": user.photo_url,
        },
    }


@router.post("/sync")
def sync_user(user: User = Depends(get_current_db_user)):
    return {
        "success": True,
        "message": "User synced successfully",
        "user": {
            "id": str(user.id),
            "firebase_uid": user.firebase_uid,
            "name": user.name,
            "email": user.email,
            "photo_url": user.photo_url,
        },
    }


# ---------------- forgot password (not signed in) ----------------

class ForgotPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class ResetPasswordRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    code: str = Field(min_length=1, max_length=20)
    new_password: str = Field(min_length=1, max_length=200)


@router.post("/password/forgot")
def forgot_password(
    data: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """Emails a reset code if an email/password account exists. Same reply either way,
    and immediately: the email itself is sent after the reply."""

    ip = request.client.host if request.client else ""

    return password_reset.request_code(
        db,
        data.email,
        ip=ip,
        send=lambda email, code: background_tasks.add_task(password_reset.send_reset_email, email, code),
    )


@router.post("/password/reset")
def reset_password(data: ResetPasswordRequest, db: Session = Depends(get_db)):
    return password_reset.reset_password(db, data.email, data.code, data.new_password)
