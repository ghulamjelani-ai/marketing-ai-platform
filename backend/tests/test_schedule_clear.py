"""Clearing finished posts (published, cancelled, removed) from the Scheduled list."""

import uuid
from datetime import datetime, timedelta

import pytest

from app.db.database import SessionLocal
from app.models.models import PublishedPost, ScheduledPost, User
from app.routers import schedule
from conftest import firebase_user


@pytest.fixture
def facebook_calls(monkeypatch):
    """Records any Facebook call; clearing must never make one."""

    calls = []
    monkeypatch.setattr(schedule.facebook_api, "delete_post", lambda *a: calls.append(("delete", a)))
    monkeypatch.setattr(schedule.facebook_api, "is_post_published", lambda *a: calls.append(("check", a)))
    return calls


def sign_in(client, login, uid=None):
    who = login(firebase_user(uid=uid))
    client.post("/auth/sync")
    with SessionLocal() as db:
        return db.query(User).filter(User.firebase_uid == who["uid"]).first().id


def add_post(user_id, status, message="Eid offer", days=-1):
    with SessionLocal() as db:
        item = ScheduledPost(
            user_id=user_id, message=message, with_image=False, status=status,
            run_at=datetime.utcnow() + timedelta(days=days), facebook_post_id=f"111_{uuid.uuid4().hex[:6]}",
            recorded=status == "published",
        )
        db.add(item)
        db.commit()
        return str(item.id)


def listed(client):
    data = client.get("/schedule").json()
    return [p["id"] for p in data["upcoming"]], [p["id"] for p in data["past"]]


@pytest.mark.parametrize("status", ["cancelled", "removed", "published"])
def test_clear_one_finished_post(client, login, facebook_calls, status):
    user = sign_in(client, login)
    post = add_post(user, status)

    response = client.delete(f"/schedule/earlier/{post}")

    assert response.status_code == 200, response.text
    assert listed(client) == ([], [])
    assert facebook_calls == []


def test_cannot_clear_a_post_still_waiting(client, login, facebook_calls):
    user = sign_in(client, login)
    post = add_post(user, "scheduled", days=2)

    response = client.delete(f"/schedule/earlier/{post}")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "POST_STILL_SCHEDULED"
    assert listed(client) == ([post], [])
    assert facebook_calls == []


def test_cannot_clear_someone_elses_post(client, login):
    owner = sign_in(client, login, uid="owner-uid")
    post = add_post(owner, "cancelled")

    sign_in(client, login, uid="other-uid")
    response = client.delete(f"/schedule/earlier/{post}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "POST_NOT_FOUND"
    with SessionLocal() as db:
        assert db.get(ScheduledPost, uuid.UUID(post)) is not None


def test_clear_twice_and_unknown_ids(client, login):
    user = sign_in(client, login)
    post = add_post(user, "cancelled")

    assert client.delete(f"/schedule/earlier/{post}").status_code == 200
    assert client.delete(f"/schedule/earlier/{post}").status_code == 404  # double click
    assert client.delete(f"/schedule/earlier/{uuid.uuid4()}").status_code == 404
    assert client.delete("/schedule/earlier/not-an-id").status_code == 422


def test_clear_all_keeps_waiting_posts_and_other_users(client, login, facebook_calls):
    other = sign_in(client, login, uid="other-uid")
    others_post = add_post(other, "cancelled")

    user = sign_in(client, login, uid="me-uid")
    waiting = add_post(user, "scheduled", days=3)
    for status in ("cancelled", "removed", "published"):
        add_post(user, status)

    response = client.post("/schedule/clear-earlier")

    assert response.json() == {"success": True, "cleared": 3}
    assert listed(client) == ([waiting], [])
    assert facebook_calls == []
    with SessionLocal() as db:
        assert db.get(ScheduledPost, uuid.UUID(others_post)) is not None

    assert client.post("/schedule/clear-earlier").json()["cleared"] == 0  # nothing left


def test_published_post_stays_in_history(client, login):
    user = sign_in(client, login)
    post = add_post(user, "published", message="Fresh bread at 7")
    with SessionLocal() as db:
        db.add(PublishedPost(user_id=user, source="scheduled", message="Fresh bread at 7", facebook_post_id="111_1"))
        db.commit()

    client.delete(f"/schedule/earlier/{post}")

    history = client.get("/history/posts").json()
    assert history["total"] == 1 and history["posts"][0]["message"] == "Fresh bread at 7"


def test_clearing_needs_sign_in(client):
    assert client.delete(f"/schedule/earlier/{uuid.uuid4()}").status_code == 401
    assert client.post("/schedule/clear-earlier").status_code == 401
