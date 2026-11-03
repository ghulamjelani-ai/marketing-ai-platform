"""Post performance: engagement of the latest published posts."""

from datetime import datetime, timedelta

import pytest

from app.db.database import SessionLocal
from app.models.models import PublishedPost, User
from app.routers import history
from conftest import firebase_user


@pytest.fixture
def facebook(monkeypatch):
    class Facebook:
        scores = {}
        asked = []

    Facebook.scores = {}
    Facebook.asked = []

    def engagement(post_id, token):
        Facebook.asked.append(post_id)
        return Facebook.scores.get(post_id)

    monkeypatch.setattr(history, "token_for_post", lambda db, user_id, post_id: "TOKEN")
    monkeypatch.setattr(history.facebook_api, "get_post_engagement", engagement)
    history.clear_insights_cache()
    yield Facebook
    history.clear_insights_cache()


def sign_in(client, login, uid=None):
    who = login(firebase_user(uid=uid))
    client.post("/auth/sync")

    with SessionLocal() as db:
        return db.query(User).filter(User.firebase_uid == who["uid"]).first().id


def publish(user_id, post_id, message="Eid sale", minutes_ago=0):
    with SessionLocal() as db:
        db.add(PublishedPost(
            user_id=user_id, source="manual", message=message, with_image=False,
            facebook_post_id=post_id, created_at=datetime.utcnow() - timedelta(minutes=minutes_ago),
        ))
        db.commit()


def test_no_posts_gives_an_empty_answer(client, login, facebook):
    sign_in(client, login)

    data = client.get("/history/insights").json()

    assert data["posts"] == [] and data["total"] == 0 and data["best_id"] is None


def test_engagement_is_totalled_and_the_best_post_found(client, login, facebook):
    user = sign_in(client, login)
    publish(user, "1_a", "First", minutes_ago=3)
    publish(user, "1_b", "Second", minutes_ago=2)
    publish(user, "1_c", "Third", minutes_ago=1)
    facebook.scores = {"1_a": 4, "1_b": 20, "1_c": 6}

    data = client.get("/history/insights").json()

    assert [p["message"] for p in data["posts"]] == ["Third", "Second", "First"]
    assert data["total"] == 30 and data["measured"] == 3 and data["average"] == 10.0
    best = next(p for p in data["posts"] if p["id"] == data["best_id"])
    assert best["message"] == "Second"


def test_a_post_facebook_cannot_answer_for_counts_as_unknown(client, login, facebook):
    user = sign_in(client, login)
    publish(user, "1_a", "Known", minutes_ago=2)
    publish(user, "1_b", "Unknown", minutes_ago=1)
    facebook.scores = {"1_a": 5}

    data = client.get("/history/insights").json()
    by_message = {p["message"]: p["engagement"] for p in data["posts"]}

    assert by_message == {"Known": 5, "Unknown": None}
    assert data["measured"] == 1 and data["total"] == 5


def test_no_engagement_at_all_names_no_best_post(client, login, facebook):
    user = sign_in(client, login)
    publish(user, "1_a")
    facebook.scores = {"1_a": 0}

    assert client.get("/history/insights").json()["best_id"] is None


def test_the_answer_is_kept_for_ten_minutes_unless_refreshed(client, login, facebook):
    user = sign_in(client, login)
    publish(user, "1_a")
    facebook.scores = {"1_a": 1}

    client.get("/history/insights")
    client.get("/history/insights")
    assert facebook.asked == ["1_a"]

    facebook.scores = {"1_a": 9}
    assert client.get("/history/insights?refresh=true").json()["total"] == 9
    assert facebook.asked == ["1_a", "1_a"]


def test_a_new_post_shows_up_even_inside_the_ten_minutes(client, login, facebook):
    user = sign_in(client, login)

    assert client.get("/history/insights").json()["posts"] == []

    publish(user, "1_new", "Just published")
    facebook.scores = {"1_new": 3}

    data = client.get("/history/insights").json()

    assert [p["message"] for p in data["posts"]] == ["Just published"] and data["total"] == 3


def test_only_the_latest_ten_posts_are_asked_about(client, login, facebook):
    user = sign_in(client, login)

    for number in range(14):
        publish(user, f"1_{number}", f"Post {number}", minutes_ago=100 - number)

    data = client.get("/history/insights").json()

    assert len(data["posts"]) == 10 and len(facebook.asked) == 10
    assert data["posts"][0]["message"] == "Post 13"


def test_other_users_posts_are_never_included(client, login, facebook):
    other = sign_in(client, login, uid="other-user")
    publish(other, "9_x", "Not mine")
    sign_in(client, login, uid="me")

    assert client.get("/history/insights").json()["posts"] == []
    assert "9_x" not in facebook.asked


def test_long_text_is_shortened(client, login, facebook):
    user = sign_in(client, login)
    publish(user, "1_a", "word " * 100)
    facebook.scores = {"1_a": 1}

    message = client.get("/history/insights").json()["posts"][0]["message"]

    assert message.endswith("...") and len(message) <= 114


def test_insights_need_a_signed_in_user(client):
    assert client.get("/history/insights").status_code == 401
