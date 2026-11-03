"""Production guards: health checks, safe headers, clean 500s, rate limits, unsafe settings."""

import pytest

import app.main as main
from app.core import ratelimit
from app.core.config import settings
from app.core.errors import ApiError
from app.routers import images, schedule
from conftest import firebase_user


def test_health_needs_no_database(client):
    response = client.get("/health")

    assert response.status_code == 200 and response.json() == {"status": "ok"}


def test_ready_checks_the_database(client):
    assert client.get("/ready").json() == {"status": "ready"}


def test_ready_says_when_the_database_is_down(client, monkeypatch):
    class Down:
        def connect(self):
            raise RuntimeError("no database")

    monkeypatch.setattr(main, "engine", Down())

    response = client.get("/ready")

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "DB_UNAVAILABLE"


def test_every_answer_has_safe_headers_and_a_request_id(client):
    response = client.get("/health")

    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["cache-control"] == "no-store"
    assert len(response.headers["x-request-id"]) >= 8
    assert "strict-transport-security" not in response.headers


def test_hsts_is_added_only_in_production(client, monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "production")

    assert "max-age" in client.get("/health").headers["strict-transport-security"]


def test_a_given_request_id_is_kept(client):
    assert client.get("/health", headers={"X-Request-ID": "abc-123"}).headers["x-request-id"] == "abc-123"


def test_an_unplanned_error_becomes_a_clean_500_the_browser_can_read(client, login, monkeypatch):
    login(firebase_user())

    def boom(db, user_id):
        raise RuntimeError("database exploded: secret-detail")

    monkeypatch.setattr(schedule, "refresh_scheduled", boom)

    response = client.get("/schedule", headers={"Origin": "http://localhost:5173"})

    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "INTERNAL_ERROR" and error["request_id"] == response.headers["x-request-id"]
    assert "secret-detail" not in response.text
    assert response.headers["access-control-allow-origin"] == "http://localhost:5173"


# ---------------------------------------------------------------- rate limits

@pytest.fixture
def limits_on(monkeypatch):
    monkeypatch.setattr(settings, "APP_ENV", "development")
    ratelimit.clear()
    yield
    ratelimit.clear()


def test_the_limit_stops_the_call_after_too_many(limits_on, monkeypatch):
    monkeypatch.setitem(ratelimit.LIMITS, "image", (2, 60))

    ratelimit.check("user-1", "image")
    ratelimit.check("user-1", "image")

    with pytest.raises(ApiError) as caught:
        ratelimit.check("user-1", "image")

    assert caught.value.status_code == 429 and caught.value.code == "RATE_LIMITED"


def test_the_limit_is_per_user_and_per_kind(limits_on, monkeypatch):
    monkeypatch.setitem(ratelimit.LIMITS, "image", (1, 60))

    ratelimit.check("user-1", "image")
    ratelimit.check("user-2", "image")
    ratelimit.check("user-1", "chat")

    with pytest.raises(ApiError):
        ratelimit.check("user-1", "image")


def test_old_calls_stop_counting(limits_on, monkeypatch):
    monkeypatch.setitem(ratelimit.LIMITS, "image", (1, 60))
    clock = {"now": 1000.0}
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: clock["now"])

    ratelimit.check("user-1", "image")
    clock["now"] += 61
    ratelimit.check("user-1", "image")


def test_the_limit_does_not_apply_in_the_test_setup():
    for _ in range(100):
        ratelimit.check("user-1", "image")


def test_the_picture_route_is_limited(client, login, limits_on, monkeypatch):
    login(firebase_user())
    client.post("/auth/sync")
    monkeypatch.setitem(ratelimit.LIMITS, "image", (2, 60))
    monkeypatch.setattr(images, "generate_image_png", lambda prompt, memory=None, enhance=True: b"\x89PNG")

    codes = [client.post("/images/generate", json={"prompt": "a bakery picture"}).status_code for _ in range(3)]

    assert codes == [200, 200, 429]


# ---------------------------------------------------------------- unsafe settings

def test_default_database_password_is_flagged(monkeypatch):
    monkeypatch.setattr(settings, "DB_PASSWORD", "12345")
    assert settings.insecure_settings() == ["DB_PASSWORD"]

    monkeypatch.setattr(settings, "DB_PASSWORD", "")
    assert settings.insecure_settings() == ["DB_PASSWORD"]

    monkeypatch.setattr(settings, "DB_PASSWORD", "a-real-secret")
    assert settings.insecure_settings() == []


# ---------------------------------------------------------------- CORS by environment

def test_production_accepts_only_the_real_site():
    origins, regex = main.cors_origins("production", "https://app.example.com")

    assert origins == ["https://app.example.com"] and regex is None


def test_development_also_accepts_local_addresses():
    import re

    origins, regex = main.cors_origins("development", "https://app.example.com")

    assert "https://app.example.com" in origins and "http://localhost:5173" in origins
    assert re.match(regex, "http://localhost:5199") and not re.match(regex, "http://evil.example.com")
