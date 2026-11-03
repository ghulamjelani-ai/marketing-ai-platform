"""One-time email codes that finish every sign-in (email/password and Google).

The code goes only to the email address in the verified Firebase ID token of the
request, never to an address the browser chooses. It is 6 random digits (secrets
module), valid for 5 minutes and usable once. Only an HMAC of it is stored and codes
are compared in constant time. After 5 wrong codes the sign-in is locked for 15
minutes. New codes need a 60 second wait, with at most 5 emails per address and 20
per IP address each hour. The code never appears in an API answer or a log line.
"""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.errors import ApiError
from app.core.mailer import send_otp_email
from app.core.secure import derived_key
from app.models.models import LoginOtp, OtpSendLog

CODE_TTL = timedelta(minutes=5)
RESEND_COOLDOWN = timedelta(seconds=60)
MAX_ATTEMPTS = 5
LOCK_TIME = timedelta(minutes=15)
MAX_SENDS_PER_EMAIL_HOUR = 5
MAX_SENDS_PER_IP_HOUR = 20

# Sign-in methods that must confirm an emailed code before a session starts.
OTP_PROVIDERS = {"google.com", "password"}


def _utcnow() -> datetime:
    # Naive UTC, like the other DateTime columns in the database.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def needs_otp(firebase_user: dict) -> bool:
    return firebase_user.get("provider") in OTP_PROVIDERS


def _hash(code: str, salt: str) -> str:
    return hmac.new(derived_key("login-otp"), f"{salt}:{code}".encode(), hashlib.sha256).hexdigest()


def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    shown = name[:2] if len(name) > 2 else name[:1]
    return f"{shown}{'*' * max(len(name) - len(shown), 1)}@{domain}"


def _row(db: Session, firebase_user: dict) -> LoginOtp | None:
    row = db.get(LoginOtp, firebase_user["uid"])

    # A row from an earlier sign-in does not count for this one.
    if row and row.auth_time != firebase_user["auth_time"]:
        return None

    return row


def _seconds(delta: timedelta) -> int:
    return max(0, int(delta.total_seconds() + 0.999))


def _locked_for(row: LoginOtp | None, now: datetime) -> int:
    if row and row.locked_until and row.locked_until > now:
        return _seconds(row.locked_until - now)

    return 0


def _wait_text(seconds: int) -> str:
    if seconds >= 90:
        return f"{(seconds + 59) // 60} minutes"

    return f"{seconds} seconds"


def is_verified(db: Session, firebase_user: dict) -> bool:
    row = _row(db, firebase_user)
    return bool(row and row.verified)


def status(db: Session, firebase_user: dict, now: datetime | None = None) -> dict:
    """What the code screen should show, read from the server (survives reloads)."""

    now = now or _utcnow()
    row = _row(db, firebase_user)
    email = firebase_user.get("email") or ""
    sent = bool(row and row.code_hash and row.expires_at > now)

    return {
        "success": True,
        "required": needs_otp(firebase_user),
        "verified": bool(row and row.verified),
        "email": mask_email(email) if email else "",
        "sent": sent,
        "expires_in": _seconds(row.expires_at - now) if sent else 0,
        "resend_in": _seconds(row.sent_at + RESEND_COOLDOWN - now) if row and row.code_hash else 0,
        "locked_for": _locked_for(row, now),
        "attempts_left": MAX_ATTEMPTS - row.attempts if sent else MAX_ATTEMPTS,
    }


def _check_send_limits(db: Session, email: str, ip: str, row: LoginOtp | None, now: datetime) -> None:
    locked = _locked_for(row, now)

    if locked:
        raise ApiError(429, "OTP_LOCKED", f"Too many wrong codes. Try again in {_wait_text(locked)}.")

    if row and row.code_hash and now - row.sent_at < RESEND_COOLDOWN:
        wait = _seconds(row.sent_at + RESEND_COOLDOWN - now)
        raise ApiError(429, "OTP_COOLDOWN", f"Please wait {wait} seconds before asking for a new code.")

    hour_ago = now - timedelta(hours=1)
    recent = db.query(OtpSendLog).filter(OtpSendLog.sent_at > hour_ago)

    if recent.filter(OtpSendLog.email == email.lower()).count() >= MAX_SENDS_PER_EMAIL_HOUR:
        raise ApiError(429, "OTP_HOURLY_LIMIT", "Too many codes were sent to this email. Please try again in an hour.")

    if ip and recent.filter(OtpSendLog.ip == ip).count() >= MAX_SENDS_PER_IP_HOUR:
        raise ApiError(429, "OTP_HOURLY_LIMIT", "Too many codes were requested from this network. Please try again later.")


def send_code(
    db: Session,
    firebase_user: dict,
    ip: str = "",
    purpose: str = "sign_in",
    now: datetime | None = None,
) -> dict:
    """Emails a new code to the signed-in user's own address and returns the new status."""

    now = now or _utcnow()
    email = firebase_user.get("email") or ""

    if not needs_otp(firebase_user):
        raise ApiError(400, "OTP_NOT_NEEDED", "This sign-in does not need an email code.")

    if not email:
        raise ApiError(400, "EMAIL_MISSING", "Your account has no email address to send a code to.")

    # Google says whether it checked the address; for email/password sign-ups the code itself proves it.
    if firebase_user.get("provider") == "google.com" and not firebase_user.get("email_verified"):
        raise ApiError(403, "EMAIL_NOT_VERIFIED", "Your Google account email is not verified. Verify it with Google and sign in again.")

    row = _row(db, firebase_user)

    if row and row.verified:
        return status(db, firebase_user, now)

    _check_send_limits(db, email, ip, row, now)

    code = new_code()
    salt = secrets.token_hex(16)
    # Send first: if the email fails, nothing changes and the user can simply try again.
    send_otp_email(email, code, purpose)

    stored = db.get(LoginOtp, firebase_user["uid"])

    if stored is None:
        stored = LoginOtp(firebase_uid=firebase_user["uid"])
        db.add(stored)

    stored.auth_time = firebase_user["auth_time"]
    stored.code_hash = _hash(code, salt)
    stored.salt = salt
    stored.expires_at = now + CODE_TTL
    stored.sent_at = now
    stored.attempts = 0
    stored.verified = False
    stored.locked_until = None

    db.add(OtpSendLog(email=email.lower(), ip=ip, sent_at=now))
    db.commit()

    return status(db, firebase_user, now)


def verify_code(db: Session, firebase_user: dict, code: str, now: datetime | None = None) -> dict:
    now = now or _utcnow()
    code = (code or "").strip()
    row = _row(db, firebase_user)

    if row is None:
        raise ApiError(400, "OTP_NOT_SENT", "Send a code to your email first.")

    if row.verified:
        return {"success": True}

    locked = _locked_for(row, now)

    if locked:
        raise ApiError(429, "OTP_LOCKED", f"Too many wrong codes. Try again in {_wait_text(locked)}.")

    if not row.code_hash or now > row.expires_at:
        raise ApiError(400, "OTP_EXPIRED", "This code has expired. Send a new code.")

    if not (len(code) == 6 and code.isdigit()) or not hmac.compare_digest(_hash(code, row.salt), row.code_hash):
        row.attempts += 1
        left = MAX_ATTEMPTS - row.attempts

        if left <= 0:
            # Lock, and throw the code away: a new one is needed after the lock.
            row.locked_until = now + LOCK_TIME
            row.code_hash = ""
            row.salt = ""
            db.commit()
            raise ApiError(429, "OTP_LOCKED", f"Too many wrong codes. Try again in {_wait_text(_seconds(LOCK_TIME))}.")

        db.commit()
        raise ApiError(400, "OTP_WRONG", f"That code is not right. {left} {'try' if left == 1 else 'tries'} left.")

    # One-time use: the hash is wiped once the code has worked.
    row.verified = True
    row.code_hash = ""
    row.salt = ""
    db.commit()

    return {"success": True}
