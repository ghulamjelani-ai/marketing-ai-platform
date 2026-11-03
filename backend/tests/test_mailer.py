"""The email service: message content, SMTP failures, retries, and a real send to the sandbox."""

import json
import smtplib
import socket
import sys
import urllib.request
from pathlib import Path

import pytest

from app.core import mailer
from app.core.errors import ApiError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))

import dev_mailbox  # noqa: E402


class FakeSMTP:
    """Stands in for smtplib.SMTP. `script` is a list of exceptions/None, one per connection."""

    script: list = []
    sent: list = []
    logins: list = []

    def __init__(self, host, port, timeout=None, **kwargs):
        self.timeout = timeout
        self.outcome = FakeSMTP.script.pop(0) if FakeSMTP.script else None

    def __enter__(self):
        if isinstance(self.outcome, (OSError, smtplib.SMTPConnectError)):
            raise self.outcome
        return self

    def __exit__(self, *args):
        return False

    def starttls(self, context=None):
        pass

    def login(self, user, password):
        FakeSMTP.logins.append(user)
        if isinstance(self.outcome, smtplib.SMTPAuthenticationError):
            raise self.outcome

    def send_message(self, message):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        FakeSMTP.sent.append((message, self.timeout))


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.script, FakeSMTP.sent, FakeSMTP.logins = [], [], []
    monkeypatch.setattr(mailer.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(mailer.time, "sleep", lambda seconds: None)
    return FakeSMTP


def test_message_has_text_html_and_no_code_in_subject(smtp):
    mailer.send_otp_email("owner@example.com", "482913", "sign_in")

    message, timeout = smtp.sent[0]
    text = message.get_body(("plain",)).get_content()
    html = message.get_body(("html",)).get_content()

    assert timeout == 10
    assert message["Subject"] == "Your Marketing AI sign-in code"
    assert message["From"] == "Marketing AI <no-reply@example.com>"
    for part in (text, html):
        assert "482913" in part and "5 minutes" in part and "didn't request this" in part
    assert smtp.logins == ["tester"]


@pytest.mark.parametrize(
    "failure,status,code",
    [
        (smtplib.SMTPAuthenticationError(535, b"5.7.8 Username and Password not accepted"), 502, "EMAIL_AUTH_FAILED"),
        (smtplib.SMTPRecipientsRefused({"owner@example.com": (550, b"5.1.1 No such user")}), 400, "EMAIL_RECIPIENT_REJECTED"),
        (smtplib.SMTPDataError(550, b"5.4.5 Daily user sending quota exceeded"), 429, "EMAIL_RATE_LIMITED"),
        (smtplib.SMTPDataError(554, b"5.7.1 Message rejected"), 502, "EMAIL_FAILED"),
    ],
    ids=["wrong-app-password", "recipient-rejected", "gmail-daily-limit", "rejected-message"],
)
def test_permanent_failures_are_not_retried(smtp, failure, status, code):
    smtp.script = [failure, None]

    with pytest.raises(ApiError) as caught:
        mailer.send_otp_email("owner@example.com", "123456")

    assert (caught.value.status_code, caught.value.code) == (status, code)
    assert smtp.script == [None]  # the second connection was never used


@pytest.mark.parametrize(
    "failure,code",
    [
        (socket.timeout("timed out"), "EMAIL_TIMEOUT"),
        (ConnectionRefusedError(10061, "refused"), "EMAIL_UNAVAILABLE"),
        (smtplib.SMTPServerDisconnected("Connection unexpectedly closed"), "EMAIL_UNAVAILABLE"),
        (smtplib.SMTPDataError(421, b"4.7.0 Try again later, too many messages"), "EMAIL_RATE_LIMITED"),
    ],
    ids=["timeout", "smtp-down", "disconnected", "temporary-rate-limit"],
)
def test_temporary_failures_are_retried_once(smtp, failure, code):
    smtp.script = [failure, failure]

    with pytest.raises(ApiError) as caught:
        mailer.send_otp_email("owner@example.com", "123456")

    assert caught.value.code == code
    assert smtp.script == []  # exactly two tries


def test_retry_succeeds_after_one_temporary_failure(smtp):
    smtp.script = [socket.timeout("timed out"), None]

    mailer.send_otp_email("owner@example.com", "123456")

    assert len(smtp.sent) == 1


def test_not_configured(monkeypatch, smtp):
    monkeypatch.setattr(mailer.settings, "SMTP_HOST", "")

    with pytest.raises(ApiError) as caught:
        mailer.send_otp_email("owner@example.com", "123456")

    assert caught.value.code == "EMAIL_NOT_CONFIGURED"
    assert smtp.sent == []


def test_logs_never_contain_code_or_password(smtp, capsys):
    smtp.script = [smtplib.SMTPAuthenticationError(535, b"bad"), None]

    with pytest.raises(ApiError):
        mailer.send_otp_email("owner@example.com", "654321")

    logs = capsys.readouterr().out
    assert "654321" not in logs
    assert "test-password" not in logs
    assert "SMTPAuthenticationError" in logs  # the detail stays on the server


@pytest.mark.parametrize(
    "env,missing",
    [
        ({"APP_ENV": "production", "SMTP_HOST": "", "SMTP_PASSWORD": ""}, ["SMTP_HOST", "SMTP_PASSWORD"]),
        ({"APP_ENV": "development", "SMTP_HOST": "", "SMTP_USERNAME": "", "SMTP_PASSWORD": ""}, ["SMTP_HOST"]),
    ],
)
def test_missing_settings_are_named(monkeypatch, env, missing):
    for name, value in env.items():
        monkeypatch.setattr(mailer.settings, name, value)

    assert mailer.settings.missing_email_settings() == missing


def test_production_refuses_to_start_without_email(monkeypatch):
    monkeypatch.setattr(mailer.settings, "APP_ENV", "production")
    monkeypatch.setattr(mailer.settings, "SMTP_PASSWORD", "")

    with pytest.raises(RuntimeError) as caught:
        mailer.check_email_settings()

    assert "SMTP_PASSWORD" in str(caught.value)
    assert "tester" not in str(caught.value)  # names only, never values


def test_development_only_warns(monkeypatch, capsys):
    monkeypatch.setattr(mailer.settings, "APP_ENV", "development")
    monkeypatch.setattr(mailer.settings, "SMTP_HOST", "")

    mailer.check_email_settings()

    assert "WARNING" in capsys.readouterr().out


def test_real_send_to_the_sandbox_inbox(monkeypatch):
    """A real SMTP conversation with the local sandbox (nothing leaves the machine)."""

    stop = dev_mailbox.start(smtp_port=1035, web_port=8035)

    try:
        for name, value in {
            "SMTP_HOST": "127.0.0.1", "SMTP_PORT": 1035, "SMTP_USERNAME": "", "SMTP_PASSWORD": "",
            "SMTP_USE_TLS": False, "SMTP_USE_SSL": False,
        }.items():
            monkeypatch.setattr(mailer.settings, name, value)

        mailer.send_otp_email("owner@example.com", "246810", "sign_up")

        inbox = json.loads(urllib.request.urlopen("http://127.0.0.1:8035/api/messages", timeout=5).read())
    finally:
        stop()

    assert len(inbox) == 1
    assert inbox[0]["to"] == ["owner@example.com"]
    assert inbox[0]["subject"] == "Your Marketing AI sign-up code"
    assert "246810" in inbox[0]["text"] and "246810" in inbox[0]["html"]


def test_sandbox_down_gives_a_clear_error(monkeypatch):
    for name, value in {
        "SMTP_HOST": "127.0.0.1", "SMTP_PORT": 1036, "SMTP_USERNAME": "", "SMTP_USE_TLS": False,
    }.items():
        monkeypatch.setattr(mailer.settings, name, value)
    monkeypatch.setattr(mailer.time, "sleep", lambda seconds: None)

    with pytest.raises(ApiError) as caught:
        mailer.send_otp_email("owner@example.com", "123456")

    assert caught.value.code == "EMAIL_UNAVAILABLE"
