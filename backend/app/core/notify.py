"""Emails the account owner about their posts.

Sent when a post is published, scheduled, goes live at its scheduled time, or is edited.
Sending never breaks the action that caused it: a failure is only logged (type and
SMTP status, never the message), and nothing is sent when email is not configured or
POST_NOTIFICATIONS is off.
"""

import html
import queue
import threading
import time
from datetime import datetime
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid

from app.core import mailer
from app.core.config import settings

# event -> (subject line, sentence above the post)
EVENTS = {
    "published": ("Your post is live", "Your post was published on {page}."),
    "scheduled": ("Your post is scheduled", "Your post is scheduled to go out on {page} at {when}."),
    "live": ("Your scheduled post is live", "Your scheduled post went live on {page}."),
    "updated": ("Your scheduled post was updated", "Your scheduled post on {page} was updated. It will go out at {when}."),
    "test": ("Test notification", "This is a test email from {page}. If you can read it, post notifications work."),
}

PREVIEW_LENGTH = 400


def _preview(text: str) -> str:
    text = (text or "").strip()

    if len(text) <= PREVIEW_LENGTH:
        return text

    return text[:PREVIEW_LENGTH].rstrip() + "..."


def _when_text(when: datetime | None) -> str:
    # `when` is a naive UTC datetime, like the database columns.
    return when.strftime("%d %b %Y, %H:%M UTC") if when else ""


def post_url(post_id: str | None) -> str:
    """A link to the post on Facebook (post ids look like PAGEID_POSTID)."""

    if post_id and "_" in post_id:
        return f"https://www.facebook.com/{post_id}"

    return ""


def build_post_email(
    to: str,
    event: str,
    page_name: str | None,
    text: str,
    when: datetime | None = None,
    link: str = "",
    with_image: bool = False,
) -> EmailMessage:
    app = settings.SMTP_FROM_NAME or "Marketing AI"
    title, sentence = EVENTS[event]
    page = page_name or "your Facebook Page"
    intro = sentence.format(page=page, when=_when_text(when))
    preview = _preview(text)

    message = EmailMessage()
    message["Subject"] = f"{app}: {title}"
    message["From"] = formataddr((app, settings.SMTP_FROM_EMAIL))
    message["To"] = to
    message["Date"] = formatdate(localtime=True)
    message["Message-ID"] = make_msgid(domain=(settings.SMTP_FROM_EMAIL.split("@")[-1] or None))
    # Marks this as an automatic notification (RFC 3834): no auto-replies, and mail systems treat it as such.
    message["Auto-Submitted"] = "auto-generated"

    plain = [intro, ""]

    if preview:
        plain += [preview, ""]

    if with_image:
        plain += ["The post includes a picture.", ""]

    if link:
        plain += [f"View it on Facebook: {link}", ""]

    plain += ["You are receiving this because you use " + app + ". Replies to this email are not read."]
    message.set_content("\n".join(plain) + "\n")

    preview_html = (
        f'<p style="margin:0 0 16px;padding:14px 16px;background:#f8f1ee;border-radius:10px;'
        f'font-size:14px;line-height:1.55;color:#2b1a1d;white-space:pre-wrap">{html.escape(preview)}</p>'
        if preview
        else ""
    )
    picture_html = (
        '<p style="margin:0 0 16px;font-size:13px;color:#4a3a3d">The post includes a picture.</p>' if with_image else ""
    )
    link_html = (
        f'<p style="margin:0 0 8px"><a href="{html.escape(link, quote=True)}" '
        'style="display:inline-block;padding:10px 18px;background:#7b1e2b;color:#ffffff;'
        'text-decoration:none;border-radius:8px;font-size:14px;font-weight:bold">View on Facebook</a></p>'
        if link
        else ""
    )

    message.add_alternative(
        f"""<!doctype html>
<html lang="en">
  <head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>{html.escape(title)}</title></head>
  <body style="margin:0;padding:0;background:#f4eeea;font-family:Arial,Helvetica,sans-serif;color:#2b1a1d">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="padding:28px 12px">
      <tr><td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:520px;background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #eadfd9">
          <tr><td style="background:#7b1e2b;padding:18px 28px">
            <p style="margin:0;font-size:18px;font-weight:bold;color:#ffffff">{html.escape(app)}</p>
          </td></tr>
          <tr><td style="padding:28px 28px 12px">
            <h1 style="margin:0 0 10px;font-size:20px;color:#2b1a1d">{html.escape(title)}</h1>
            <p style="margin:0 0 18px;font-size:15px;line-height:1.5;color:#4a3a3d">{html.escape(intro)}</p>
            {preview_html}{picture_html}{link_html}
          </td></tr>
          <tr><td style="padding:16px 28px 22px;border-top:1px solid #f0e6e2">
            <p style="margin:0;font-size:12px;line-height:1.5;color:#8a7a7d">You are receiving this because you use {html.escape(app)}. Replies to this email are not read.</p>
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


def email_enabled(user_id) -> bool:
    """The user's own switch for post emails (on unless they turned it off)."""

    from app.db.database import SessionLocal
    from app.models.models import UserPreference

    try:
        with SessionLocal() as db:
            row = db.get(UserPreference, user_id)
            return True if row is None else bool(row.email_notifications)
    except Exception as exc:  # noqa: BLE001 - a broken lookup must not block the email
        print(f"Notification preference lookup failed: {type(exc).__name__}")
        return True


def record(user_id, event: str, status: str, detail: str = "", text: str = "") -> None:
    """Keeps a short history of what happened to each email so the owner can see it."""

    if not user_id:
        return

    from app.db.database import SessionLocal
    from app.models.models import NotificationLog

    try:
        with SessionLocal() as db:
            db.add(
                NotificationLog(
                    user_id=user_id,
                    event=event,
                    status=status,
                    detail=(detail or "")[:80],
                    preview=_preview(text)[:160],
                )
            )
            db.commit()
    except Exception as exc:  # noqa: BLE001
        print(f"Notification log not saved: {type(exc).__name__}")


def post_event(
    to: str | None,
    event: str,
    *,
    user_id=None,
    page_name: str | None = None,
    text: str = "",
    when: datetime | None = None,
    post_id: str | None = None,
    with_image: bool = False,
) -> bool:
    """Sends one notification. Returns True when an email went out; never raises.

    With a user_id the result is also kept in the user's notification history, and the
    user's own on/off switch is respected.
    """

    if not to:
        record(user_id, event, "skipped", "NO_EMAIL", text)
        return False

    if not settings.POST_NOTIFICATIONS:
        record(user_id, event, "skipped", "DISABLED_BY_ADMIN", text)
        return False

    if user_id and not email_enabled(user_id):
        record(user_id, event, "skipped", "TURNED_OFF", text)
        return False

    if not mailer.email_configured():
        record(user_id, event, "skipped", "NOT_CONFIGURED", text)
        return False

    try:
        mailer.send_message(
            build_post_email(to, event, page_name, text, when, post_url(post_id), with_image)
        )
    except Exception as exc:  # noqa: BLE001 - a notification must never break a post
        code = getattr(exc, "code", "") or type(exc).__name__
        print(f"Post notification not sent: {type(exc).__name__} {code}")
        record(user_id, event, "failed", str(code), text)
        return False

    record(user_id, event, "sent", "", text)
    return True


# ---------------------------------------------------------------- the worker

# Emails are sent by one background thread, not inside the request that caused them. A slow
# mail server then never slows a post down, and a web request that ends early can never
# drop an email. A job that fails is logged (and kept in the notification history) and the
# worker carries on with the next one.
_jobs: "queue.Queue[tuple]" = queue.Queue()
_worker_lock = threading.Lock()
_worker: threading.Thread | None = None


def _work() -> None:
    while True:
        to, event, kwargs = _jobs.get()

        try:
            post_event(to, event, **kwargs)
        except Exception as exc:  # noqa: BLE001 - nothing may stop the worker
            print(f"Post notification worker error: {type(exc).__name__}")
        finally:
            _jobs.task_done()


def _ensure_worker() -> None:
    global _worker

    with _worker_lock:
        if _worker is None or not _worker.is_alive():
            _worker = threading.Thread(target=_work, name="post-notifications", daemon=True)
            _worker.start()


def submit(to: str | None, event: str, **kwargs) -> None:
    """Queues one notification for the worker. Returns at once and never raises."""

    if settings.NOTIFY_INLINE:
        post_event(to, event, **kwargs)
        return

    _ensure_worker()
    _jobs.put((to, event, kwargs))


def flush(timeout: float = 10.0) -> bool:
    """Waits until every queued email was handled. For shutdown and tests; True when done."""

    deadline = time.monotonic() + timeout

    while _jobs.unfinished_tasks:
        if time.monotonic() > deadline:
            return False

        time.sleep(0.02)

    return True
