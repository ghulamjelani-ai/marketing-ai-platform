"""Connecting Facebook keeps every Page; the user chooses which one posts go to."""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core.secure import decrypt_text
from app.db.database import SessionLocal
from app.models.models import FacebookConnection, FacebookPage, ScheduledPost, User
from app.routers import facebook
from conftest import firebase_user

PAGES = [
    {"id": "111", "name": "Lahore Bakery", "access_token": "TOKEN-111"},
    {"id": "222", "name": "Cake Corner", "access_token": "TOKEN-222"},
    {"id": "333", "name": "No Token Page"},  # Facebook gave no token: cannot be used
]


class FakeGraph:
    """Answers the two Graph calls of the connect callback, and records publishes."""

    def __init__(self, monkeypatch, pages):
        self.pages = pages
        self.published = []
        self.deleted = []
        monkeypatch.setattr(facebook.requests, "get", self.get)
        monkeypatch.setattr(facebook, "FACEBOOK_APP_ID", "app")
        monkeypatch.setattr(facebook, "FACEBOOK_APP_SECRET", "secret")
        monkeypatch.setattr(facebook.facebook_api, "publish_text", self.publish_text)
        monkeypatch.setattr(facebook.facebook_api, "delete_post", self.delete_post)

    def get(self, url, params=None, timeout=None):
        if url.endswith("/oauth/access_token"):
            return SimpleNamespace(status_code=200, json=lambda: {"access_token": "USER-TOKEN"})
        return SimpleNamespace(status_code=200, json=lambda: {"data": self.pages})

    def publish_text(self, page_id, token, message, scheduled_at=None):
        self.published.append((page_id, token))
        return {"id": f"{page_id}_9{len(self.published)}"}

    def delete_post(self, post_id, token):
        self.deleted.append((post_id, token))


@pytest.fixture
def user(client, login):
    who = login(firebase_user())
    client.post("/auth/sync")
    with SessionLocal() as db:
        return db.query(User).filter(User.firebase_uid == who["uid"]).first().id


def connect(client, user_id):
    response = client.get(
        "/facebook/callback",
        params={"code": "abc", "state": facebook.make_state(user_id)},
        follow_redirects=False,
    )
    assert response.status_code in (302, 307), response.text
    return response.headers["location"]


def pages(client):
    return client.get("/facebook/pages").json()["pages"]


def test_connect_saves_every_usable_page(client, user, monkeypatch):
    FakeGraph(monkeypatch, PAGES)

    location = connect(client, user)

    assert location.endswith("facebook=connected&pages=2")
    listed = pages(client)
    assert [p["page_name"] for p in listed] == ["Cake Corner", "Lahore Bakery"]
    assert [p["selected"] for p in listed] == [False, True]  # first Page is the default

    status = client.get("/facebook/status").json()
    assert status["page_name"] == "Lahore Bakery" and status["page_count"] == 2

    with SessionLocal() as db:
        tokens = [row.token_encrypted for row in db.query(FacebookPage).all()]
    assert all("TOKEN" not in t for t in tokens)  # stored encrypted
    assert sorted(decrypt_text(t) for t in tokens) == ["TOKEN-111", "TOKEN-222"]


def test_choose_page_and_publish_there(client, user, monkeypatch):
    graph = FakeGraph(monkeypatch, PAGES)
    connect(client, user)

    chosen = client.post("/facebook/select-page", json={"page_id": "222"})

    assert chosen.json()["page_name"] == "Cake Corner"
    assert client.get("/facebook/status").json()["page_name"] == "Cake Corner"

    client.post("/facebook/publish", json={"message": "Weekend cake sale"})

    assert graph.published == [("222", "TOKEN-222")]


def test_cannot_choose_someone_elses_page(client, user, monkeypatch):
    FakeGraph(monkeypatch, PAGES)
    connect(client, user)

    response = client.post("/facebook/select-page", json={"page_id": "999"})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "PAGE_NOT_FOUND"
    assert client.get("/facebook/status").json()["page_id"] == "111"


def test_reconnect_keeps_the_chosen_page(client, user, monkeypatch):
    FakeGraph(monkeypatch, PAGES)
    connect(client, user)
    client.post("/facebook/select-page", json={"page_id": "222"})

    connect(client, user)

    assert client.get("/facebook/status").json()["page_id"] == "222"


def test_reconnect_when_chosen_page_is_gone(client, user, monkeypatch):
    graph = FakeGraph(monkeypatch, PAGES)
    connect(client, user)
    client.post("/facebook/select-page", json={"page_id": "222"})

    graph.pages = [PAGES[0]]
    connect(client, user)

    assert client.get("/facebook/status").json()["page_id"] == "111"
    assert len(pages(client)) == 1


def test_no_usable_pages(client, user, monkeypatch):
    FakeGraph(monkeypatch, [PAGES[2]])

    response = client.get(
        "/facebook/callback",
        params={"code": "abc", "state": facebook.make_state(user)},
        follow_redirects=False,
    )

    assert response.status_code == 400


def test_cancel_uses_the_posts_own_page_after_switching(client, user, monkeypatch):
    graph = FakeGraph(monkeypatch, PAGES)
    connect(client, user)

    with SessionLocal() as db:
        item = ScheduledPost(
            user_id=user, message="Eid offer", with_image=False,
            run_at=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=1),
            facebook_post_id="111_555", status="scheduled",
        )
        db.add(item)
        db.commit()
        post_id = item.id

    client.post("/facebook/select-page", json={"page_id": "222"})
    response = client.delete(f"/schedule/{post_id}")

    assert response.status_code == 200, response.text
    assert graph.deleted == [("111_555", "TOKEN-111")]


def test_disconnect_forgets_every_page(client, user, monkeypatch):
    FakeGraph(monkeypatch, PAGES)
    connect(client, user)

    client.post("/facebook/disconnect")

    assert pages(client) == []
    assert client.get("/facebook/status").json()["connected"] is False
    with SessionLocal() as db:
        assert db.query(FacebookPage).count() == 0
        assert db.query(FacebookConnection).count() == 0


def test_pages_need_sign_in(client):
    assert client.get("/facebook/pages").status_code == 401
    assert client.post("/facebook/select-page", json={"page_id": "111"}).status_code == 401
