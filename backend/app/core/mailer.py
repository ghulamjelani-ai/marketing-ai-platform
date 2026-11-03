"""Sends the 6-digit sign-in code by email through the SMTP server set in backend/.env.

Works with any SMTP provider (Gmail with an App Password, a transactional provider) and
with the local sandbox inbox (tools/dev_mailbox.py or Mailpit on localhost:1025).

Failures become clear API errors with a code; the technical detail is logged on the
server only. Neither the code nor any SMTP password is ever logged.
"""

import smtplib
import socket
import ssl
import time
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from app.core.config import settings
from app.core.errors import ApiError

PURPOSES = {
    "sign_in": "sign-in",
    "sign_up": "sign-up",
    "password_reset": "password reset",
}

# The line above the code in the email, per purpose.
INSTRUCTIONS = {
    "password_reset": "Enter this code to choose a new password:",
}

# 4xx answers are temporary by definition; these words mean a sending limit was hit.
_RATE_WORDS = ("rate", "limit", "quota", "too many")


def email_configured() -> bool:
    return not settings.missing_email_settings()


def check_email_settings() -> None:
    """Runs at startup. Production stops with the missing names; development only warns."""

    missing = settings.missing_email_settings()

    if not missing:
        return

    names = ", ".join(missing)

    if settings.APP_ENV == "production":
        raise RuntimeError(
            f"Email sending is not configured. Set these in backend/.env: {names}. "
            "Sign-in codes cannot be sent without them."
        )

    print(
        f"WARNING: email sending is not configured ({names} missing in backend/.env). "
        "Sign-in codes cannot be sent. For local testing run the sandbox inbox "
        "(backend/tools/dev_mailbox.py) and set SMTP_HOST=localhost, SMTP_PORT=1025."
    )


def build_otp_email(to: str, code: str, purpose: str = "sign_in") -> EmailMessage:
    app = settings.SMTP_FROM_NAME or "Marketing AI"
    action = PURPOSES.get(purpose, "sign-in")

    message = EmailMessage()
    # The code stays out of the subject, which shows up in mail logs and notifications.
    message["Subject"] = f"Your {app} {action} code"
    message["From"] = formataddr((app, settings.SMTP_FROM_EMAIL))
    message["To"] = to
    # A missing Date header is a common spam signal.
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=(settings.SMTP_FROM_EMAIL.split("@")[-1] or None))

    message.set_content(
        f"Your {app} {action} code is: {code}\n\n"
        "It expires in 5 minutes and can be used once.\n\n"
        "If you didn't request this, ignore this email.\n"
    )

    instruction = INSTRUCTIONS.get(purpose, "Enter this code to finish signing in:")

    message.add_alternative(
        f"""<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Your {action} code</title></head>
  <body style="margin:0;padding:0;background:#f4eeea;font-family:Arial,Helvetica,sans-serif;color:#2b1a1d">
    <span style="display:none;max-height:0;overflow:hidden">Your {app} {action} code expires in 5 minutes.</span>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:28px 12px">
      <tr><td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #eadfd9">
          <tr><td style="background:#7b1e2b;padding:18px 28px">
            <p style="margin:0;font-size:18px;font-weight:bold;color:#ffffff;letter-spacing:0.5px">{app}</p>
          </td></tr>
          <tr><td style="padding:28px 28px 10px">
            <h1 style="margin:0 0 10px;font-size:20px;color:#2b1a1d">Your {action} code</h1>
            <p style="margin:0 0 18px;font-size:15px;line-height:1.5;color:#4a3a3d">{instruction}</p>
            <p style="margin:0 0 18px;padding:16px 0;background:#f8f1ee;border:1px dashed #c9a9a0;border-radius:10px;text-align:center;font-size:32px;letter-spacing:6px;font-weight:bold;color:#7b1e2b;font-family:'Courier New',monospace">{code}</p>
            <p style="margin:0 0 6px;font-size:14px;color:#4a3a3d">It expires in <strong>5 minutes</strong> and can be used once.</p>
            <p style="margin:0 0 22px;font-size:14px;color:#4a3a3d">Never share this code with anyone.</p>
          </td></tr>
          <tr><td style="padding:16px 28px 22px;border-top:1px solid #f0e6e2">
            <p style="margin:0;font-size:12px;line-height:1.5;color:#8a7a7d">If you didn't request this, ignore this email. Your account stays safe.</p>
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
""",
        subtype="html",
    )

    return message


def _deliver(message: EmailMessage) -> None:
    timeout = settings.SMTP_TIMEOUT
    context = ssl.create_default_context()

    if settings.SMTP_USE_SSL:
        server = smtplib.SMTP_SSL(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout, context=context)
    else:
        server = smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=timeout)

    with server:
        if settings.SMTP_USE_TLS and not settings.SMTP_USE_SSL:
            server.starttls(context=context)

        if settings.SMTP_USERNAME:
            server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)

        server.send_message(message)


def _is_rate_limit(exc: smtplib.SMTPResponseException) -> bool:
    text = (exc.smtp_error or b"").decode(errors="ignore").lower() if isinstance(exc.smtp_error, bytes) else str(exc.smtp_error).lower()
    return exc.smtp_code in (421, 450, 451, 452) or any(word in text for word in _RATE_WORDS)


def _is_transient(exc: Exception) -> bool:
    if isinstance(exc, (socket.timeout, TimeoutError, ConnectionError, smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError)):
        return True

    return isinstance(exc, smtplib.SMTPResponseException) and 400 <= exc.smtp_code < 500


def _log(exc: Exception, attempt: int) -> None:
    """Server-side detail only: type and SMTP status, never the message body or passwords."""

    status = getattr(exc, "smtp_code", "")
    print(f"Email attempt {attempt} failed: {type(exc).__name__} {status} (host {settings.SMTP_HOST}:{settings.SMTP_PORT})")


def _api_error(exc: Exception) -> ApiError:
    if isinstance(exc, smtplib.SMTPAuthenticationError):
        print("Email: the SMTP login was refused. Check SMTP_USERNAME and SMTP_PASSWORD (Gmail needs an App Password).")
        return ApiError(502, "EMAIL_AUTH_FAILED", "We couldn't send the email right now. Please try again later.")

    if isinstance(exc, smtplib.SMTPRecipientsRefused):
        return ApiError(400, "EMAIL_RECIPIENT_REJECTED", "This email address can't receive our messages. Check the address or use another account.")

    if isinstance(exc, smtplib.SMTPResponseException) and _is_rate_limit(exc):
        return ApiError(429, "EMAIL_RATE_LIMITED", "Too many emails are being sent right now. Please wait a few minutes and send a new code.")

    if isinstance(exc, (socket.timeout, TimeoutError)):
        return ApiError(504, "EMAIL_TIMEOUT", "The email server took too long to answer. Please send a new code.")

    # Checked before OSError: every smtplib error is also an OSError.
    if isinstance(exc, smtplib.SMTPResponseException) and not isinstance(exc, smtplib.SMTPConnectError):
        return ApiError(502, "EMAIL_FAILED", "We couldn't send the email. Please send a new code.")

    if isinstance(exc, (OSError, smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError)):
        return ApiError(502, "EMAIL_UNAVAILABLE", "We couldn't reach the email server. Please send a new code in a moment.")

    return ApiError(502, "EMAIL_FAILED", "We couldn't send the email. Please send a new code.")


def send_otp_email(to: str, code: str, purpose: str = "sign_in") -> None:
    """Sends the code. Raises ApiError with a clear code if it cannot be delivered.

    Each try is limited by SMTP_TIMEOUT (10 s); a temporary failure is retried once.
    """

    if not email_configured():
        raise ApiError(
            503,
            "EMAIL_NOT_CONFIGURED",
            "Email sending is not set up yet, so we can't send your code. Please try again later.",
        )

    send_message(build_otp_email(to, code, purpose))


def send_message(message: EmailMessage) -> None:
    """Delivers a built email with the same timeout, retry and error codes as the sign-in code."""

    for attempt in (1, 2):
        try:
            _deliver(message)
            return
        except smtplib.SMTPRecipientsRefused as exc:
            _log(exc, attempt)
            raise _api_error(exc) from None
        except (smtplib.SMTPException, OSError) as exc:
            _log(exc, attempt)

            if attempt == 1 and _is_transient(exc) and not isinstance(exc, smtplib.SMTPAuthenticationError):
                time.sleep(1)
                continue

            raise _api_error(exc) from None
