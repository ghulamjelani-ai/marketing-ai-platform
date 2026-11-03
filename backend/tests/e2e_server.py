"""Test backend for the browser (E2E) tests, on http://127.0.0.1:8010.

The real FastAPI app with every outside service faked:
- a fresh SQLite file instead of PostgreSQL,
- Firebase tokens of the form "e2e:<provider>:<auth_time>:<uid>:<email>",
- OpenAI (topic check, post, picture, best time, memory) answered locally,
- Facebook calls recorded, never sent,
- login emails really sent over SMTP, to the local sandbox inbox (tools/dev_mailbox.py on
  SMTP port 1045, web/API port 8045), so nothing reaches a real address.

Extra /__e2e/* routes let the test read what happened and switch on failures.
Never run this against real data.
"""

import base64
from urllib.parse import unquote
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine  # noqa: E402

from app.db import database  # noqa: E402

DB_FILE = Path(tempfile.gettempdir()) / "marketing_ai_e2e.sqlite"
DB_FILE.unlink(missing_ok=True)
ENGINE = create_engine(f"sqlite:///{DB_FILE}", connect_args={"check_same_thread": False})
database.engine = ENGINE
database.SessionLocal.configure(bind=ENGINE)

import uvicorn  # noqa: E402
from fastapi import HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402

import app.main as main  # noqa: E402
from app.core import idempotency, otp  # noqa: E402
from app.core.errors import ApiError  # noqa: E402
from app.core.facebook_api import FacebookError  # noqa: E402
from app.db.database import Base  # noqa: E402
from app.routers import auth, autopilot, chat, facebook, images, memory, schedule, voice  # noqa: E402

Base.metadata.create_all(bind=ENGINE)

main.app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5198"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# A 1x1 PNG is enough for the browser to show a picture.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)

state = {
    "ai_calls": [],
    "fb_calls": [],
    "fail": {},
    "password_changes": [],  # name -> how many times it should still fail
}


def should_fail(name: str) -> bool:
    left = state["fail"].get(name, 0)

    if left:
        state["fail"][name] = left - 1
        return True

    return False


# ---------------- Firebase ----------------

def fake_firebase_user(authorization: str | None = auth.Header(default=None)):
    token = (authorization or "").removeprefix("Bearer ").strip()
    parts = token.split(":")

    if len(parts) != 6 or parts[0] != "e2e":
        raise HTTPException(status_code=401, detail="Invalid or expired Firebase token")

    _, provider, auth_time, uid, email, name = parts
    return {
        "uid": uid,
        "email": email,
        "name": unquote(name) or None,
        "picture": None,
        "email_verified": "unverified" not in email,
        "auth_time": int(auth_time),
        "provider": provider,
    }


main.app.dependency_overrides[auth.get_current_firebase_user] = fake_firebase_user


# ---------------- OpenAI ----------------

def fake_intent(topic):
    state["ai_calls"].append(("intent", topic))
    return {"valid": "lorem" not in topic.lower(), "reason": "This is placeholder text"}


def fake_post(topic, memory_text):
    state["ai_calls"].append(("post", topic))

    if should_fail("post"):
        raise ApiError(504, "AI_TIMEOUT", "The AI took too long to answer. Please try again.")

    return {
        "caption": f"E2E caption about {topic}",
        "description": "E2E description.",
        "hashtags": ["#E2E", "#Test", "#Sale"],
        "image_prompt": "A bright test photo.",
        "language": "English",
    }


def fake_image(prompt, memory_text=None, enhance=True):
    state["ai_calls"].append(("image", prompt))

    if should_fail("image"):
        raise ApiError(502, "AI_UNAVAILABLE", "Could not reach the AI service. Check the internet connection and try again.")

    return PNG


autopilot.check_topic_intent = fake_intent
autopilot.draft_single_post = fake_post
autopilot.update_memory_in_background = lambda *args: None
images.generate_image_png = fake_image
schedule.suggest_post_times = lambda memory_text: [{"time": "18:00", "label": "Evening", "reason": "E2E"}]
memory.update_memory_summary = lambda current, message: current or ""

VOICE_TEXT = "I run a bakery in Lahore and want more customers"


def fake_transcribe(audio, filename, content_type, memory_text=None):
    state["ai_calls"].append(("voice", len(audio), content_type))

    if should_fail("voice"):
        raise ApiError(502, "AI_UNAVAILABLE", "Could not reach the AI service. Check the internet connection and try again.")

    return VOICE_TEXT


def fake_chat_reply(user_message, **kwargs):
    state["ai_calls"].append(("chat", user_message))
    return f"Sure, here is a plan for {user_message}. Post one is ready below."


voice.transcribe_audio = fake_transcribe
chat.generate_marketing_ai_reply = fake_chat_reply
chat.update_memory_in_background = lambda *args, **kwargs: None

# ---------------- Facebook ----------------

PAGE = SimpleNamespace(page_id="PAGE", page_name="E2E Test Page")


def fake_connection(db, user_id):
    """The chosen Page if the test gave the user Pages, otherwise the one default test Page."""

    from app.models.models import FacebookConnection

    row = db.query(FacebookConnection).filter(FacebookConnection.user_id == user_id).first()
    return (row, "TOKEN-" + row.page_id) if row else (PAGE, "TOKEN")


facebook.get_user_connection = fake_connection
schedule.get_user_connection = fake_connection


def fb_failure():
    if should_fail("fb401"):
        raise FacebookError(400, {"message": "x", "facebook_response": {"error": {"code": 190, "message": "expired"}}})


def fake_publish_text(page_id, token, message, scheduled_at=None):
    fb_failure()
    state["fb_calls"].append({"type": "text", "message": message, "scheduled": scheduled_at is not None, "page": page_id})
    return {"id": f"PAGE_T{len(state['fb_calls'])}"}


def fake_publish_photo(page_id, token, image_bytes, filename, content_type, message, scheduled_at=None):
    fb_failure()
    state["fb_calls"].append({"type": "photo", "message": message, "scheduled": scheduled_at is not None, "page": page_id})
    return {"id": f"PH{len(state['fb_calls'])}", "post_id": f"PAGE_P{len(state['fb_calls'])}"}


def fake_update_post(post_id, token, message=None, scheduled_at=None):
    fb_failure()
    state["fb_calls"].append({"type": "update", "post": post_id, "message": message, "scheduled": scheduled_at is not None})


facebook.facebook_api.update_post = fake_update_post
facebook.facebook_api.publish_text = fake_publish_text
facebook.facebook_api.publish_photo = fake_publish_photo
facebook.facebook_api.delete_post = lambda post_id, token: None
facebook.facebook_api.is_post_published = lambda post_id, token: None
facebook.facebook_api.get_post_engagement = lambda post_id, token: None

# ---------------- Email ----------------

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import dev_mailbox  # noqa: E402
from app.core.config import settings  # noqa: E402

SANDBOX = "http://127.0.0.1:8045/api/messages"
dev_mailbox.start(smtp_port=1045, web_port=8045)

settings.APP_ENV = "test"
settings.SMTP_HOST = "127.0.0.1"
settings.SMTP_PORT = 1045
settings.SMTP_USERNAME = ""
settings.SMTP_PASSWORD = ""
settings.SMTP_FROM_EMAIL = "no-reply@marketing-ai.local"
settings.SMTP_USE_TLS = False
settings.SMTP_USE_SSL = False
settings.POST_NOTIFICATIONS = False
settings.NOTIFY_INLINE = True
settings.BACKGROUND_POLLER = False

real_send_otp_email = otp.send_otp_email


def send_or_fail(to, code, purpose="sign_in"):
    if should_fail("email"):
        raise ApiError(503, "EMAIL_NOT_CONFIGURED", "Email sending is not set up yet, so we can't send your code. Please try again later.")

    real_send_otp_email(to, code, purpose)


otp.send_otp_email = send_or_fail

# Forgot password: one email/password account exists; new passwords are recorded, not set.
from app.core import firebase as firebase_admin_helpers  # noqa: E402
from app.core import password_reset  # noqa: E402

password_reset.send_otp_email = send_or_fail
firebase_admin_helpers.find_account = lambda email: {"reset.owner@example.com": "pw-reset-owner", "owner@gmail.com": "google-owner"}.get(email)
firebase_admin_helpers.set_password = lambda uid, password: state["password_changes"].append(uid)


def sandbox_messages():
    import json
    import urllib.request

    return json.loads(urllib.request.urlopen(SANDBOX, timeout=5).read())


# ---------------- control routes (test only) ----------------

@main.app.get("/__e2e/state")
def e2e_state():
    return state | {"emails": len(sandbox_messages())}


@main.app.post("/__e2e/seed_pages")
def e2e_seed_pages():
    """Gives every existing user two Facebook Pages, the first one chosen."""

    from app.core.secure import encrypt_text
    from app.models.models import FacebookConnection, FacebookPage, User

    with database.SessionLocal() as db:
        for user in db.query(User).all():
            for page_id, name in (("111", "Lahore Bakery"), ("222", "Cake Corner")):
                db.add(FacebookPage(user_id=user.id, page_id=page_id, page_name=name, token_encrypted=encrypt_text("TOKEN-" + page_id)))
            db.add(FacebookConnection(user_id=user.id, page_id="111", page_name="Lahore Bakery", token_encrypted=encrypt_text("TOKEN-111")))
        db.commit()

    return {"ok": True}


@main.app.post("/__e2e/seed_earlier")
def e2e_seed_earlier():
    """Gives every user one waiting post and three finished ones (plus the published one in History)."""

    from datetime import datetime, timedelta

    from app.models.models import PublishedPost, ScheduledPost, User

    now = datetime.utcnow()

    with database.SessionLocal() as db:
        for user in db.query(User).all():
            db.add(ScheduledPost(user_id=user.id, message="Waiting post for Friday", status="scheduled",
                                 run_at=now + timedelta(days=2), facebook_post_id=PAGE.page_id + "_w1"))
            for i, (status, text) in enumerate((("cancelled", "Cancelled tax offer"),
                                                ("removed", "Removed Eid post"),
                                                ("published", "Published bread post"))):
                db.add(ScheduledPost(user_id=user.id, message=text, status=status, recorded=status == "published",
                                     run_at=now - timedelta(days=i + 1), facebook_post_id=f"{PAGE.page_id}_e{i}"))
            db.add(PublishedPost(user_id=user.id, source="scheduled", message="Published bread post",
                                 facebook_post_id=PAGE.page_id + "_e2", created_at=now - timedelta(days=3)))
        db.commit()

    return {"ok": True}


@main.app.get("/__e2e/users")
def e2e_users():
    from app.models.models import User

    with database.SessionLocal() as db:
        return [{"email": u.email, "name": u.name} for u in db.query(User).all()]


@main.app.get("/__e2e/last_code")
def e2e_last_code():
    import re

    import time

    # Some emails go out in the background after the reply; wait for them briefly.
    for _ in range(50):
        messages = sandbox_messages()
        if messages:
            break
        time.sleep(0.1)

    latest = messages[0]
    return {"code": re.search(r"\b(\d{6})\b", latest["text"]).group(1), "to": latest["to"], "subject": latest["subject"]}


@main.app.post("/__e2e/reset")
def e2e_reset():
    state["ai_calls"].clear()
    state["fb_calls"].clear()
    import urllib.request

    urllib.request.urlopen(urllib.request.Request(SANDBOX, method="DELETE"), timeout=5)
    state["fail"].clear()
    state["password_changes"].clear()
    idempotency.clear()

    with database.SessionLocal() as db:
        for table in reversed(Base.metadata.sorted_tables):
            db.execute(table.delete())
        db.commit()

    return {"ok": True}


@main.app.post("/__e2e/fail/{name}/{times}")
def e2e_fail(name: str, times: int):
    state["fail"][name] = times
    return {"ok": True}


@main.app.post("/__e2e/expire_otp")
async def e2e_expire_otp(request: Request):
    from datetime import timedelta

    from app.models.models import LoginOtp

    with database.SessionLocal() as db:
        for row in db.query(LoginOtp).all():
            row.expires_at -= timedelta(minutes=10)
            row.sent_at -= timedelta(minutes=10)
        db.commit()

    return {"ok": True}


if __name__ == "__main__":
    uvicorn.run(main.app, host="127.0.0.1", port=8010, log_level="warning")
