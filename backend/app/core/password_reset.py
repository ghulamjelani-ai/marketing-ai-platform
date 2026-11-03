"""Forgot password: a 6-digit code emailed to the account, then a new password.

The person is not signed in here, so the answers never reveal whether an account exists:
asking for a code always gets the same reply, and a wrong, expired or never-sent code
gets the same message. Codes follow the sign-in code rules (see otp.py): HMAC only,
5 minutes, single use, 5 wrong tries lock for 15 minutes, 60 seconds between sends and
hourly caps per address and per IP.
"""

import hmac
import re
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.core import firebase, otp
from app.core.errors import ApiError
from app.core.mailer import email_configured, send_otp_email
from app.models.models import OtpSendLog, PasswordReset

MIN_PASSWORD = 8
SPECIAL = re.compile(r"[^A-Za-z0-9]")


def password_problem(password: str) -> str | None:
    """Same rules as the sign-up page (frontend/src/utils/passwordRules.js)."""

    missing = []

    if len(password) < MIN_PASSWORD:
        missing.append(f"at least {MIN_PASSWORD} characters")
    if not re.search(r"[A-Z]", password):
        missing.append("a capital letter")
    if not re.search(r"[a-z]", password):
        missing.append("a small letter")
    if not re.search(r"[0-9]", password):
        missing.append("a number")
    if not SPECIAL.search(password):
        missing.append("a special character such as ! @ # $")

    if not missing:
        return None

    return "Your password needs " + ", ".join(missing[:-1]) + (" and " if len(missing) > 1 else "") + missing[-1] + "."
EMAIL = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]{2,}$")

SENT_REPLY = {
    "success": True,
    "message": "If an account exists for this email, we sent it a 6-digit code. It expires in 5 minutes.",
    "resend_in": int(otp.RESEND_COOLDOWN.total_seconds()),
    "expires_in": int(otp.CODE_TTL.total_seconds()),
}

BAD_CODE = "That code is not right or has expired. Check the email or send a new code."


def _clean(email: str) -> str:
    email = (email or "").strip().lower()

    if not EMAIL.match(email):
        raise ApiError(400, "EMAIL_INVALID", "Please enter a valid email address.")

    return email


def _hash(code: str, salt: str) -> str:
    return otp._hash(code, "reset:" + salt)


def send_reset_email(email: str, code: str) -> None:
    """Runs after the reply has gone out, so the page never waits for the mail server."""

    try:
        send_otp_email(email, code, "password_reset")
    except ApiError as error:
        # Only logged: the reply must not show whether the account exists.
        print("Password reset email failed:", error.code)


def request_code(db: Session, email: str, ip: str = "", now: datetime | None = None, send=None) -> dict:
    """Saves a new code if the account exists and hands the email to `send(email, code)`.

    `send` is normally a background task, so the reply is instant either way.
    """
    now = now or otp._utcnow()
    email = _clean(email)

    # Not about one account, so saying it reveals nothing.
    if not email_configured():
        raise ApiError(503, "EMAIL_NOT_CONFIGURED", "Email sending is not set up yet, so we can't send your code. Please try again later.")

    row = db.get(PasswordReset, email)

    if row and row.locked_until and row.locked_until > now:
        return SENT_REPLY

    # Within 60 seconds nothing new is sent. A "please wait" answer would only ever
    # appear for real accounts, so the reply stays the same (the page counts down anyway).
    if row and now - row.sent_at < otp.RESEND_COOLDOWN:
        return SENT_REPLY

    hour_ago = now - timedelta(hours=1)
    recent = db.query(OtpSendLog).filter(OtpSendLog.sent_at > hour_ago)

    if ip and recent.filter(OtpSendLog.ip == ip).count() >= otp.MAX_SENDS_PER_IP_HOUR:
        raise ApiError(429, "OTP_HOURLY_LIMIT", "Too many codes were requested from this network. Please try again later.")

    if recent.filter(OtpSendLog.email == email).count() >= otp.MAX_SENDS_PER_EMAIL_HOUR:
        return SENT_REPLY

    uid = firebase.find_account(email)

    if uid is None:
        return SENT_REPLY

    code = otp.new_code()
    salt = secrets.token_hex(16)

    if row is None:
        row = PasswordReset(email=email)
        db.add(row)

    row.firebase_uid = uid
    row.code_hash = _hash(code, salt)
    row.salt = salt
    row.expires_at = now + otp.CODE_TTL
    row.sent_at = now
    row.attempts = 0
    row.locked_until = None

    db.add(OtpSendLog(email=email, ip=ip, sent_at=now))
    db.commit()

    (send or send_reset_email)(email, code)

    return SENT_REPLY


def reset_password(db: Session, email: str, code: str, new_password: str, now: datetime | None = None) -> dict:
    now = now or otp._utcnow()
    email = _clean(email)
    code = (code or "").strip()

    problem = password_problem(new_password or "")

    if problem:
        raise ApiError(400, "PASSWORD_WEAK", problem)

    row = db.get(PasswordReset, email)

    if row and row.locked_until and row.locked_until > now:
        wait = otp._wait_text(otp._seconds(row.locked_until - now))
        raise ApiError(429, "OTP_LOCKED", f"Too many wrong codes. Try again in {wait}.")

    if row is None or not row.code_hash or now > row.expires_at:
        raise ApiError(400, "OTP_WRONG", BAD_CODE)

    if not (len(code) == 6 and code.isdigit()) or not hmac.compare_digest(_hash(code, row.salt), row.code_hash):
        row.attempts += 1

        if row.attempts >= otp.MAX_ATTEMPTS:
            row.locked_until = now + otp.LOCK_TIME
            row.code_hash = ""
            db.commit()
            raise ApiError(429, "OTP_LOCKED", "Too many wrong codes. Try again in 15 minutes.")

        db.commit()
        raise ApiError(400, "OTP_WRONG", BAD_CODE)

    firebase.set_password(row.firebase_uid, new_password)

    # One-time use.
    db.delete(row)
    db.commit()

    return {"success": True, "message": "Your password has been changed. Log in with your new password."}
