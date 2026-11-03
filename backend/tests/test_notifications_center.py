"""The owner's notification page: on/off switch, test email and the delivery history."""

from datetime import datetime, timedelta

import pytest

from app.core import mailer, notify
from app.core.errors import ApiError
from app.db.database import SessionLocal
from app.models.models import NotificationLog, User
from conftest import firebase_user


@pytest.fixture
def mail(monkeypatch):
    """Switches post emails on and captures them; mail.fail makes the next send fail."""

    class Mail:
        sent = []
        fail = None

    monkeypatch.setattr(notify.settings, "POST_NOTIFICATIONS", True)
    Mail.sent = []
    Mail.fail = None

    def send(message):
        if Mail.fail:
            raise Mail.fail

        Mail.sent.append(message)

    monkeypatch.setattr(mailer, "send_message", send)
    return Mail


def sign_in(client, login, uid=None):
    who = login(firebase_user(uid=uid))
    client.post("/auth/sync")

    with SessionLocal() as db:
        return db.query(User).filter(User.firebase_uid == who["uid"]).first().id


def history(user_id):
    with SessionLocal() as db:
        rows = db.query(NotificationLog).filter(NotificationLog.user_id == user_id).order_by(NotificationLog.id).all()
        return [(r.event, r.status, r.detail) for r in rows]


# ---------------------------------------------------------------- delivery history

def test_a_sent_email_is_recorded(client, login, mail):
    user = sign_in(client, login)

    assert notify.post_event("a@example.com", "published", user_id=user, text="Eid sale") is True
    assert history(user) == [("published", "sent", "")]


def test_a_failed_email_is_recorded_with_its_reason(client, login, mail):
    user = sign_in(client, login)
    mail.fail = ApiError(502, "EMAIL_AUTH_FAILED", "x")

    assert notify.post_event("a@example.com", "published", user_id=user, text="Eid sale") is False
    assert history(user) == [("published", "failed", "EMAIL_AUTH_FAILED")]


def test_an_unexpected_error_is_recorded_by_its_type(client, login, mail):
    user = sign_in(client, login)
    mail.fail = RuntimeError("boom")

    assert notify.post_event("a@example.com", "live", user_id=user) is False
    assert history(user) == [("live", "failed", "RuntimeError")]


def test_skipped_emails_say_why(client, login, mail, monkeypatch):
    user = sign_in(client, login)

    notify.post_event("", "published", user_id=user)
    monkeypatch.setattr(notify.settings, "SMTP_HOST", "")
    notify.post_event("a@example.com", "published", user_id=user)
    monkeypatch.setattr(notify.settings, "POST_NOTIFICATIONS", False)
    notify.post_event("a@example.com", "published", user_id=user)

    assert [row[2] for row in history(user)] == ["NO_EMAIL", "NOT_CONFIGURED", "DISABLED_BY_ADMIN"]
    assert mail.sent == []


def test_calls_without_a_user_leave_no_history(client, login, mail):
    assert notify.post_event("a@example.com", "published", text="x") is True

    with SessionLocal() as db:
        assert db.query(NotificationLog).count() == 0


# ---------------------------------------------------------------- the switch

def test_overview_starts_with_emails_on(client, login, mail):
    sign_in(client, login)

    data = client.get("/notifications").json()

    assert data["email_enabled"] is True and data["items"] == []
    assert "@example.com" in data["address"] and "*" in data["address"]
    assert data["server_ready"] is True


def test_turning_emails_off_stops_them_and_says_so(client, login, mail):
    user = sign_in(client, login)

    assert client.put("/notifications/settings", json={"email_enabled": False}).json()["email_enabled"] is False
    assert client.get("/notifications").json()["email_enabled"] is False

    assert notify.post_event("a@example.com", "published", user_id=user) is False
    assert mail.sent == [] and history(user) == [("published", "skipped", "TURNED_OFF")]

    client.put("/notifications/settings", json={"email_enabled": True})
    assert notify.post_event("a@example.com", "published", user_id=user) is True


def test_the_switch_is_per_user(client, login, mail):
    first = sign_in(client, login, uid="user-a")
    client.put("/notifications/settings", json={"email_enabled": False})
    second = sign_in(client, login, uid="user-b")

    assert client.get("/notifications").json()["email_enabled"] is True
    assert notify.post_event("b@example.com", "published", user_id=second) is True
    assert notify.post_event("a@example.com", "published", user_id=first) is False


def test_history_lists_newest_first_with_reasons_and_only_my_own(client, login, mail):
    mine = sign_in(client, login, uid="mine")
    other = sign_in(client, login, uid="other")
    notify.post_event("o@example.com", "published", user_id=other, text="not mine")
    login(firebase_user(uid="mine"))

    mail.fail = ApiError(502, "EMAIL_TIMEOUT", "x")
    notify.post_event("a@example.com", "scheduled", user_id=mine, text="first")
    mail.fail = None
    notify.post_event("a@example.com", "published", user_id=mine, text="second")

    items = client.get("/notifications").json()["items"]

    assert [i["preview"] for i in items] == ["second", "first"]
    assert items[0]["status"] == "sent" and items[0]["reason"] == ""
    assert items[1]["status"] == "failed" and "too long" in items[1]["reason"]


# ---------------------------------------------------------------- the test email

def test_test_email_goes_to_the_owner(client, login, mail):
    user = sign_in(client, login)

    response = client.post("/notifications/test")

    assert response.status_code == 200, response.text
    assert "*" in response.json()["sent_to"]
    assert len(mail.sent) == 1 and "Test notification" in mail.sent[0]["Subject"]
    assert history(user) == [("test", "sent", "")]


def test_test_email_reports_the_real_problem(client, login, mail):
    user = sign_in(client, login)
    mail.fail = ApiError(502, "EMAIL_AUTH_FAILED", "We couldn't send the email right now. Please send a new code.")

    response = client.post("/notifications/test")

    assert response.status_code == 502
    error = response.json()["error"]
    assert error["code"] == "EMAIL_AUTH_FAILED" and "administrator" in error["message"]
    assert history(user) == [("test", "failed", "EMAIL_AUTH_FAILED")]


def test_test_email_needs_a_configured_server(client, login, mail, monkeypatch):
    sign_in(client, login)
    monkeypatch.setattr(notify.settings, "SMTP_HOST", "")

    response = client.post("/notifications/test")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EMAIL_NOT_CONFIGURED"


def test_test_email_cannot_be_spammed(client, login, mail):
    sign_in(client, login)

    assert client.post("/notifications/test").status_code == 200
    again = client.post("/notifications/test")

    assert again.status_code == 429 and again.json()["error"]["code"] == "TEST_COOLDOWN"
    assert len(mail.sent) == 1


def test_test_email_works_again_after_the_cooldown(client, login, mail):
    user = sign_in(client, login)
    client.post("/notifications/test")

    with SessionLocal() as db:
        for row in db.query(NotificationLog).filter(NotificationLog.user_id == user):
            row.created_at = datetime.utcnow() - timedelta(minutes=5)

        db.commit()

    assert client.post("/notifications/test").status_code == 200


def test_the_notification_routes_need_a_signed_in_user(client):
    assert client.get("/notifications").status_code == 401
    assert client.put("/notifications/settings", json={"email_enabled": False}).status_code == 401
    assert client.post("/notifications/test").status_code == 401
