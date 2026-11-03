"""Email codes that finish every sign-in (email/password and Google)."""

import re
from datetime import timedelta

import pytest

from app.core import otp
from app.db.database import SessionLocal
from app.models.models import LoginOtp, OtpSendLog, User
from conftest import firebase_user


@pytest.fixture
def google(login):
    return login(firebase_user(provider="google.com", email="owner@gmail.com"), verified=False)


@pytest.fixture
def password_user(login):
    # Firebase does not mark email/password addresses as verified; the code proves them.
    return login(firebase_user(provider="password", email="shop@example.com", verified=False), verified=False)


def code_from(outbox):
    return re.search(r"\b(\d{6})\b", outbox[-1].body).group(1)


def send(client, purpose=None):
    return client.post("/auth/otp/send", json={"purpose": purpose} if purpose else None)


def verify(client, code):
    return client.post("/auth/otp/verify", json={"code": code})


def status(client):
    return client.get("/auth/otp/status").json()


def move_clock(uid, **delta):
    """Pretend everything for this user happened earlier."""

    with SessionLocal() as db:
        row = db.get(LoginOtp, uid)
        row.sent_at -= timedelta(**delta)
        row.expires_at -= timedelta(**delta)
        if row.locked_until:
            row.locked_until -= timedelta(**delta)
        for log in db.query(OtpSendLog).all():
            log.sent_at -= timedelta(**delta)
        db.commit()


def wrong(code):
    return "000000" if code != "000000" else "111111"


# ---------------- who needs a code ----------------

@pytest.mark.parametrize("provider", ["google.com", "password"])
def test_every_sign_in_needs_a_code_before_any_session(client, login, provider):
    login(firebase_user(provider=provider), verified=False)

    response = client.post("/auth/sync")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "OTP_REQUIRED"

    with SessionLocal() as db:
        assert db.query(User).count() == 0  # no account until the code is confirmed


def test_nothing_is_sent_until_asked(client, google, sent_emails):
    body = status(client)

    assert body["required"] and not body["sent"] and not body["verified"]
    assert body["email"] == "ow***@gmail.com"
    assert sent_emails == []


# ---------------- sending ----------------

def test_full_success(client, google, sent_emails, capsys):
    response = send(client)

    assert response.status_code == 200
    body = response.json()
    assert body["sent"] and body["expires_in"] == 300 and body["resend_in"] == 60

    code = code_from(sent_emails)
    assert sent_emails[-1].to == "owner@gmail.com"
    assert code not in response.text
    assert code not in sent_emails[-1].subject

    with SessionLocal() as db:
        row = db.get(LoginOtp, google["uid"])
        assert code not in (row.code_hash, row.salt)
        assert len(row.code_hash) == 64  # HMAC-SHA256

    ok = verify(client, code)

    assert ok.status_code == 200
    assert code not in ok.text
    assert client.post("/auth/sync").status_code == 200
    assert code not in capsys.readouterr().out


def test_password_sign_up_gets_a_code_without_firebase_verification(client, password_user, sent_emails):
    response = send(client, "sign_up")

    assert response.status_code == 200
    assert sent_emails[-1].to == "shop@example.com"
    assert "sign-up" in sent_emails[-1].subject
    assert verify(client, code_from(sent_emails)).status_code == 200
    assert client.post("/auth/sync").status_code == 200


def test_code_goes_only_to_the_token_email(client, google, sent_emails):
    """The browser cannot choose the address: extra fields are ignored."""

    response = client.post("/auth/otp/send", json={"purpose": "sign_in", "email": "victim@example.com", "to": "x@y.z"})

    assert response.status_code == 200
    assert [mail.to for mail in sent_emails] == ["owner@gmail.com"]


def test_bad_purpose_is_refused(client, google, sent_emails):
    assert send(client, "anything").status_code == 422
    assert sent_emails == []


def test_code_is_six_random_digits():
    codes = {otp.new_code() for _ in range(200)}

    assert all(re.fullmatch(r"\d{6}", c) for c in codes)
    assert len(codes) > 190


def test_unverified_google_email_is_refused(client, login, sent_emails):
    login(firebase_user(provider="google.com", verified=False), verified=False)

    response = send(client)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "EMAIL_NOT_VERIFIED"
    assert sent_emails == []


# ---------------- requests without a valid sign-in ----------------

def test_requires_a_firebase_token(client, sent_emails):
    for call in (lambda: send(client), lambda: verify(client, "123456"), lambda: client.get("/auth/otp/status")):
        assert call().status_code == 401

    assert sent_emails == []


def test_invalid_or_expired_token(client, sent_emails, monkeypatch):
    from fastapi import HTTPException

    from app.routers import auth

    def reject(id_token):
        raise HTTPException(status_code=401, detail="Invalid or expired Firebase token")

    monkeypatch.setattr(auth, "verify_firebase_token", reject)

    response = client.post("/auth/otp/send", headers={"Authorization": "Bearer expired.token.value"})

    assert response.status_code == 401
    assert sent_emails == []


# ---------------- checking codes ----------------

def test_wrong_code(client, google, sent_emails):
    send(client)
    response = verify(client, wrong(code_from(sent_emails)))

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_WRONG"
    assert "4 tries left" in response.json()["error"]["message"]
    assert client.post("/auth/sync").status_code == 403


def test_expired_code(client, google, sent_emails):
    send(client)
    code = code_from(sent_emails)
    move_clock(google["uid"], minutes=6)

    response = verify(client, code)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "OTP_EXPIRED"
    assert not status(client)["sent"]


def test_five_wrong_codes_lock_for_15_minutes(client, google, sent_emails):
    send(client)
    code = code_from(sent_emails)

    answers = [verify(client, wrong(code)).json()["error"]["code"] for _ in range(5)]

    assert answers == ["OTP_WRONG"] * 4 + ["OTP_LOCKED"]
    assert "15 minutes" in verify(client, code).json()["error"]["message"]
    assert 14 * 60 < status(client)["locked_for"] <= 15 * 60

    # No new code during the lock either.
    move_clock(google["uid"], minutes=2)
    assert send(client).json()["error"]["code"] == "OTP_LOCKED"

    # After 15 minutes a new code can be sent and works.
    move_clock(google["uid"], minutes=14)
    assert send(client).status_code == 200
    assert verify(client, code_from(sent_emails)).status_code == 200


def test_code_is_one_time_use(client, google, sent_emails):
    send(client)
    code = code_from(sent_emails)

    assert verify(client, code).status_code == 200

    with SessionLocal() as db:
        row = db.get(LoginOtp, google["uid"])
        assert row.code_hash == "" and row.verified


def test_new_sign_in_needs_a_new_code(client, login, sent_emails):
    user = login(firebase_user(provider="google.com", auth_time=1000), verified=False)
    send(client)
    verify(client, code_from(sent_emails))
    assert client.post("/auth/sync").status_code == 200

    login({**user, "auth_time": 2000}, verified=False)

    assert client.post("/auth/sync").status_code == 403


def test_verify_without_send(client, google):
    assert verify(client, "123456").json()["error"]["code"] == "OTP_NOT_SENT"


# ---------------- sending limits ----------------

def test_resend_waits_60_seconds(client, google, sent_emails):
    send(client)
    too_soon = send(client)

    assert too_soon.status_code == 429
    assert too_soon.json()["error"]["code"] == "OTP_COOLDOWN"
    assert len(sent_emails) == 1

    move_clock(google["uid"], seconds=61)

    assert send(client).status_code == 200
    assert len(sent_emails) == 2


def test_resend_invalidates_the_old_code(client, google, sent_emails, monkeypatch):
    codes = iter(["111111", "222222"])
    monkeypatch.setattr(otp, "new_code", lambda: next(codes))

    send(client)
    move_clock(google["uid"], seconds=61)
    send(client)

    assert verify(client, "111111").json()["error"]["code"] == "OTP_WRONG"
    assert verify(client, "222222").status_code == 200


def test_five_emails_per_address_per_hour(client, google, sent_emails):
    for _ in range(5):
        assert send(client).status_code == 200
        move_clock(google["uid"], seconds=61)

    capped = send(client)

    assert capped.status_code == 429
    assert capped.json()["error"]["code"] == "OTP_HOURLY_LIMIT"
    assert len(sent_emails) == 5

    move_clock(google["uid"], minutes=60)
    assert send(client).status_code == 200


def test_limit_per_ip_address(client, login, sent_emails):
    for i in range(otp.MAX_SENDS_PER_IP_HOUR):
        login(firebase_user(provider="password", email=f"user{i}@example.com"), verified=False)
        assert send(client).status_code == 200

    login(firebase_user(provider="password", email="one.more@example.com"), verified=False)
    capped = send(client)

    assert capped.status_code == 429
    assert capped.json()["error"]["code"] == "OTP_HOURLY_LIMIT"


def test_status_restores_the_screen_after_a_reload(client, google, sent_emails):
    send(client)
    move_clock(google["uid"], seconds=20)

    body = status(client)

    assert body["sent"] and 279 <= body["expires_in"] <= 281 and 39 <= body["resend_in"] <= 41


# ---------------- email failures ----------------

def test_email_failure_changes_nothing(client, google, monkeypatch):
    from app.core.errors import ApiError

    def broken(*args):
        raise ApiError(504, "EMAIL_TIMEOUT", "The email server took too long to answer. Please send a new code.")

    monkeypatch.setattr(otp, "send_otp_email", broken)

    response = send(client)

    assert response.status_code == 504
    assert response.json()["error"]["code"] == "EMAIL_TIMEOUT"
    # No cooldown starts when nothing was sent: the user can try again at once.
    assert not status(client)["sent"] and status(client)["resend_in"] == 0


def test_email_not_configured(client, google, monkeypatch):
    from app.core import mailer

    monkeypatch.setattr(mailer.settings, "SMTP_HOST", "")

    response = send(client)

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "EMAIL_NOT_CONFIGURED"
    assert "SMTP" not in response.json()["error"]["message"]  # no server details for users


# ---------------- small helpers ----------------

def test_mask_email():
    assert otp.mask_email("owner@gmail.com") == "ow***@gmail.com"
    assert otp.mask_email("a@gmail.com") == "a*@gmail.com"


def test_limits():
    assert otp.CODE_TTL == timedelta(minutes=5)
    assert otp.RESEND_COOLDOWN == timedelta(seconds=60)
    assert otp.MAX_ATTEMPTS == 5
    assert otp.LOCK_TIME == timedelta(minutes=15)
    assert otp.MAX_SENDS_PER_EMAIL_HOUR == 5


def test_concurrent_first_sync_does_not_fail(login):
    """Two sync calls for a new user at the same moment both succeed (one row)."""

    from app.routers.auth import get_or_create_user

    user = firebase_user()
    first, second = SessionLocal(), SessionLocal()

    assert first.query(User).filter(User.firebase_uid == user["uid"]).first() is None
    get_or_create_user(first, user)

    original_query = second.query
    calls = {"n": 0}

    def stale_first_lookup(*args, **kwargs):
        calls["n"] += 1
        query = original_query(*args, **kwargs)
        return query.filter(False) if calls["n"] == 1 else query

    second.query = stale_first_lookup
    row = get_or_create_user(second, {**user, "name": "Umer Irfan"})

    assert row.firebase_uid == user["uid"]
    assert row.name == "Umer Irfan"  # the losing call still saves its data

    with SessionLocal() as db:
        assert db.query(User).count() == 1

    first.close()
    second.close()
