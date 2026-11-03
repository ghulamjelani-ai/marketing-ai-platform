"""Emails are sent by a background worker, so a request never waits for the mail server."""

import threading
import time

import pytest

from app.core import mailer, notify
from app.db.database import SessionLocal
from app.models.models import NotificationLog, User
from conftest import firebase_user


@pytest.fixture
def worker(monkeypatch):
    """Production behaviour: jobs are queued, not sent inside the call."""

    monkeypatch.setattr(notify.settings, "NOTIFY_INLINE", False)
    monkeypatch.setattr(notify.settings, "POST_NOTIFICATIONS", True)
    assert notify.flush(5)
    yield
    assert notify.flush(5)


def test_submit_returns_before_the_email_is_sent(worker, monkeypatch):
    gate = threading.Event()
    sent = []

    def slow_send(message):
        gate.wait(5)
        sent.append(message)

    monkeypatch.setattr(mailer, "send_message", slow_send)

    started = time.monotonic()
    notify.submit("a@example.com", "published", text="Eid sale")

    assert time.monotonic() - started < 1
    assert sent == []

    gate.set()
    assert notify.flush(5)
    assert len(sent) == 1


def test_queued_emails_are_all_sent_in_order(worker, monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send_message", lambda message: sent.append(str(message["To"])))

    for number in range(5):
        notify.submit(f"user{number}@example.com", "published", text="x")

    assert notify.flush(5)
    assert sent == [f"user{number}@example.com" for number in range(5)]


def test_a_failing_email_does_not_stop_the_next_one(worker, monkeypatch):
    sent = []

    def flaky(message):
        if str(message["To"]).startswith("bad"):
            raise RuntimeError("mail server down")

        sent.append(str(message["To"]))

    monkeypatch.setattr(mailer, "send_message", flaky)

    notify.submit("bad@example.com", "published", text="first")
    notify.submit("good@example.com", "published", text="second")

    assert notify.flush(5)
    assert sent == ["good@example.com"]


def test_a_crash_inside_a_job_does_not_kill_the_worker(worker, monkeypatch):
    calls = []

    def explode_once(to, event, **kwargs):
        calls.append(to)

        if to == "first@example.com":
            raise ValueError("unexpected")

    monkeypatch.setattr(notify, "post_event", explode_once)

    notify.submit("first@example.com", "published")
    notify.submit("second@example.com", "published")

    assert notify.flush(5)
    assert calls == ["first@example.com", "second@example.com"]


def test_the_result_lands_in_the_history_after_the_worker_ran(client, login, worker, monkeypatch):
    who = login(firebase_user())
    client.post("/auth/sync")

    with SessionLocal() as db:
        user_id = db.query(User).filter(User.firebase_uid == who["uid"]).first().id

    monkeypatch.setattr(mailer, "send_message", lambda message: None)

    notify.submit("a@example.com", "published", user_id=user_id, text="Eid sale")
    assert notify.flush(5)

    with SessionLocal() as db:
        rows = db.query(NotificationLog).filter(NotificationLog.user_id == user_id).all()

    assert [(r.event, r.status) for r in rows] == [("published", "sent")]


def test_flush_gives_up_after_the_timeout(worker, monkeypatch):
    gate = threading.Event()
    monkeypatch.setattr(mailer, "send_message", lambda message: gate.wait(5))

    notify.submit("a@example.com", "published", text="x")

    assert notify.flush(0.2) is False

    gate.set()
    assert notify.flush(5)
