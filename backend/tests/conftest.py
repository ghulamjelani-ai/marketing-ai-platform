"""Shared test setup.

Every test runs against an in-memory SQLite database (never the real PostgreSQL),
with Firebase, OpenAI, email and Facebook replaced by fakes. Nothing leaves the
machine and nothing is published.
"""

import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Keep real keys out of the tests even if backend/.env has them.
os.environ["OPENAI_API_KEY"] = "test-key"
os.environ["APP_ENV"] = "test"
os.environ["SMTP_HOST"] = "smtp.test"
os.environ["SMTP_USERNAME"] = "tester"
os.environ["SMTP_PASSWORD"] = "test-password"
os.environ["SMTP_FROM_EMAIL"] = "no-reply@example.com"

from app.db import database  # noqa: E402

TEST_ENGINE = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
database.engine = TEST_ENGINE
database.SessionLocal.configure(bind=TEST_ENGINE)

from fastapi.testclient import TestClient  # noqa: E402

from app.core import idempotency, mailer  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.db.database import Base  # noqa: E402
import app.main as main  # noqa: E402
from app.routers import auth as auth_router  # noqa: E402

settings.OPENAI_API_KEY = "test-key"
settings.APP_ENV = "test"
settings.SMTP_HOST = "smtp.test"
settings.SMTP_PORT = 587
settings.SMTP_USERNAME = "tester"
settings.SMTP_PASSWORD = "test-password"
settings.SMTP_FROM_EMAIL = "no-reply@example.com"
settings.SMTP_FROM_NAME = "Marketing AI"
settings.SMTP_TIMEOUT = 10
settings.SMTP_USE_TLS = True
settings.SMTP_USE_SSL = False
# Tests never send post notification emails unless a test switches them on with a fake.
settings.POST_NOTIFICATIONS = False
settings.NOTIFY_INLINE = True
settings.BACKGROUND_POLLER = False


def firebase_user(provider="password", email=None, verified=True, auth_time=1000, uid=None):
    uid = uid or f"uid-{uuid.uuid4().hex[:8]}"
    return {
        "uid": uid,
        "email": email or f"{uid}@example.com",
        "name": "Test User",
        "picture": None,
        "email_verified": verified,
        "auth_time": auth_time,
        "provider": provider,
    }


@pytest.fixture(autouse=True)
def fresh_db():
    Base.metadata.drop_all(bind=TEST_ENGINE)
    Base.metadata.create_all(bind=TEST_ENGINE)
    idempotency.clear()
    yield
    main.app.dependency_overrides.clear()


@pytest.fixture
def sent_emails(monkeypatch):
    """Captures emails instead of sending them."""

    outbox = []

    def fake_send(to, code, purpose="sign_in"):
        message = mailer.build_otp_email(to, code, purpose)
        outbox.append(SimpleNamespace(to=to, subject=message["Subject"], body=message.get_body(("plain",)).get_content()))

    monkeypatch.setattr("app.core.otp.send_otp_email", fake_send)
    monkeypatch.setattr("app.core.password_reset.send_otp_email", fake_send)
    return outbox


@pytest.fixture
def client():
    return TestClient(main.app)


@pytest.fixture
def login(client):
    """login(user_dict) makes every request act as that Firebase user.

    With verified=True (the default) the user's emailed code counts as confirmed, so tests
    of other features start signed in; OTP tests pass verified=False.
    """

    def as_user(user, verified=True):
        main.app.dependency_overrides[auth_router.get_current_firebase_user] = lambda: user

        if verified:
            from datetime import datetime

            from app.models.models import LoginOtp

            with database.SessionLocal() as db:
                db.merge(LoginOtp(
                    firebase_uid=user["uid"], auth_time=user["auth_time"], code_hash="", salt="",
                    expires_at=datetime(2000, 1, 1), sent_at=datetime(2000, 1, 1), attempts=0, verified=True,
                ))
                db.commit()

        return user

    return as_user
