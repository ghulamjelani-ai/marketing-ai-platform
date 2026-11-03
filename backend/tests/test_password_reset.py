"""Forgot password: code by email, then a new password. Firebase is faked."""

import re
from datetime import timedelta

import pytest

from app.core import firebase, password_reset
from app.db.database import SessionLocal
from app.models.models import OtpSendLog, PasswordReset

ACCOUNTS = {"shop@example.com": "uid-shop", "owner@gmail.com": "uid-google-only"}


@pytest.fixture
def accounts(monkeypatch):
    changed = []
    monkeypatch.setattr(firebase, "find_account", lambda email: ACCOUNTS.get(email))
    monkeypatch.setattr(firebase, "set_password", lambda uid, password: changed.append((uid, password)))
    return changed


def forgot(client, email="shop@example.com"):
    return client.post("/auth/password/forgot", json={"email": email})


def reset(client, code, password="New-secret-1", email="shop@example.com"):
    return client.post("/auth/password/reset", json={"email": email, "code": code, "new_password": password})


def code_from(outbox):
    return re.search(r"\b(\d{6})\b", outbox[-1].body).group(1)


def move_clock(email="shop@example.com", **delta):
    with SessionLocal() as db:
        row = db.get(PasswordReset, email)
        row.sent_at -= timedelta(**delta)
        row.expires_at -= timedelta(**delta)
        if row.locked_until:
            row.locked_until -= timedelta(**delta)
        for log in db.query(OtpSendLog).all():
            log.sent_at -= timedelta(**delta)
        db.commit()


def wrong(code):
    return "000000" if code != "000000" else "111111"


def test_full_reset(client, accounts, sent_emails):
    response = forgot(client, "  Shop@Example.com ")

    assert response.status_code == 200
    assert sent_emails[-1].to == "shop@example.com"
    assert "password reset" in sent_emails[-1].subject
    code = code_from(sent_emails)
    assert code not in response.text

    done = reset(client, code)

    assert done.status_code == 200
    assert accounts == [("uid-shop", "New-secret-1")]
    assert code not in done.text


def test_same_reply_whether_or_not_the_account_exists(client, accounts, sent_emails):
    known = forgot(client, "shop@example.com")
    unknown = forgot(client, "nobody@example.com")

    assert known.status_code == unknown.status_code == 200
    assert known.json() == unknown.json()
    assert [mail.to for mail in sent_emails] == ["shop@example.com"]


def test_quick_second_request_looks_the_same(client, accounts, sent_emails):
    first = forgot(client)
    second = forgot(client)

    assert first.json() == second.json()
    assert len(sent_emails) == 1  # nothing new within 60 seconds


def test_code_is_single_use(client, accounts, sent_emails):
    forgot(client)
    code = code_from(sent_emails)

    assert reset(client, code).status_code == 200
    assert reset(client, code, "Another-pass-2").json()["error"]["code"] == "OTP_WRONG"
    assert len(accounts) == 1


def test_wrong_and_unknown_get_the_same_message(client, accounts, sent_emails):
    forgot(client)
    wrong_answer = reset(client, wrong(code_from(sent_emails)))
    never_sent = reset(client, "123456", email="nobody@example.com")

    assert wrong_answer.status_code == never_sent.status_code == 400
    assert wrong_answer.json() == never_sent.json()
    assert accounts == []


def test_expired_code(client, accounts, sent_emails):
    forgot(client)
    code = code_from(sent_emails)
    move_clock(minutes=6)

    assert reset(client, code).json()["error"]["code"] == "OTP_WRONG"
    assert accounts == []


def test_five_wrong_codes_lock_for_15_minutes(client, accounts, sent_emails):
    forgot(client)
    code = code_from(sent_emails)

    answers = [reset(client, wrong(code)).json()["error"]["code"] for _ in range(5)]

    assert answers == ["OTP_WRONG"] * 4 + ["OTP_LOCKED"]
    assert reset(client, code).json()["error"]["code"] == "OTP_LOCKED"
    assert accounts == []

    move_clock(minutes=16)
    forgot(client)
    assert reset(client, code_from(sent_emails)).status_code == 200


@pytest.mark.parametrize(
    "weak,missing",
    [
        ("Sh0rt!", "at least 8 characters"),
        ("lowercase-only1", "a capital letter"),
        ("UPPERCASE-ONLY1", "a small letter"),
        ("No-Numbers-Here", "a number"),
        ("NoSpecial123", "a special character"),
    ],
)
def test_weak_passwords_are_refused(client, accounts, sent_emails, weak, missing):
    forgot(client)

    response = reset(client, code_from(sent_emails), password=weak)

    assert response.json()["error"]["code"] == "PASSWORD_WEAK"
    assert missing in response.json()["error"]["message"]
    assert accounts == []


def test_google_only_account_can_set_a_password(client, accounts, sent_emails):
    forgot(client, "owner@gmail.com")

    assert sent_emails[-1].to == "owner@gmail.com"
    assert reset(client, code_from(sent_emails), email="owner@gmail.com").status_code == 200
    assert accounts == [("uid-google-only", "New-secret-1")]


def test_email_has_a_date_header(sent_emails):
    from app.core import mailer

    assert mailer.build_otp_email("a@example.com", "123456")["Date"]


def test_invalid_email(client, accounts, sent_emails):
    assert forgot(client, "not-an-email").json()["error"]["code"] == "EMAIL_INVALID"
    assert sent_emails == []


def test_hourly_cap_is_silent(client, accounts, sent_emails):
    for _ in range(5):
        forgot(client)
        move_clock(seconds=61)

    capped = forgot(client)

    assert capped.status_code == 200  # same reply, nothing sent
    assert len(sent_emails) == 5


def test_email_failure_does_not_reveal_the_account(client, accounts, monkeypatch):
    from app.core.errors import ApiError

    def broken(*args):
        raise ApiError(502, "EMAIL_AUTH_FAILED", "x")

    monkeypatch.setattr(password_reset, "send_otp_email", broken)

    assert forgot(client).json() == forgot(client, "nobody@example.com").json()


def test_email_not_configured_is_said_plainly(client, accounts, monkeypatch):
    from app.core import mailer

    monkeypatch.setattr(mailer.settings, "SMTP_HOST", "")

    assert forgot(client).json()["error"]["code"] == "EMAIL_NOT_CONFIGURED"


def test_needs_no_sign_in(client, accounts, sent_emails):
    """Forgot password works while signed out (no Authorization header)."""

    assert forgot(client).status_code == 200


def test_new_password_does_not_lock_out_new_logins(monkeypatch):
    """Regression: revoking sessions with this computer's clock (3 minutes fast) made every
    login fail with "sign-in expired" right after a reset. Only the password is updated."""

    calls = []

    class FakeFirebaseAuth:
        @staticmethod
        def update_user(uid, **fields):
            calls.append(("update_user", uid, sorted(fields)))

        @staticmethod
        def revoke_refresh_tokens(uid):
            calls.append(("revoke_refresh_tokens", uid))

    monkeypatch.setattr(firebase, "firebase_auth", FakeFirebaseAuth)
    monkeypatch.setattr(firebase, "get_firebase_app", lambda: None)

    firebase.set_password("uid-1", "New-secret-1")

    assert calls == [("update_user", "uid-1", ["password"])]
