"""Post notification emails, editing scheduled posts, and the background live check."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.core import mailer, notify
from app.core.facebook_api import FacebookError
from app.db.database import SessionLocal
from app.models.models import ScheduledPost, User
from app.routers import facebook, schedule
from conftest import firebase_user


# ---------------------------------------------------------------- the email itself

def test_email_has_text_link_and_escapes_html():
    message = notify.build_post_email(
        "owner@example.com", "published", "Lahore Bakery", "Sale <script>alert(1)</script> today",
        link="https://www.facebook.com/111_222", with_image=True,
    )

    plain = message.get_body(("plain",)).get_content()
    page = message.get_body(("html",)).get_content()

    assert message["To"] == "owner@example.com"
    assert "Your post is live" in message["Subject"]
    assert "Lahore Bakery" in plain and "https://www.facebook.com/111_222" in plain
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "The post includes a picture." in plain


def test_email_is_marked_as_automatic():
    message = notify.build_post_email("o@example.com", "published", "P", "Hi")

    assert message["Auto-Submitted"] == "auto-generated"


def test_scheduled_email_names_the_time():
    when = datetime(2026, 12, 1, 18, 30)
    message = notify.build_post_email("o@example.com", "scheduled", None, "Hello", when=when)

    assert "01 Dec 2026, 18:30 UTC" in message.get_body(("plain",)).get_content()
    assert "your Facebook Page" in message.get_body(("plain",)).get_content()


def test_long_text_is_cut_in_the_preview():
    message = notify.build_post_email("o@example.com", "published", "P", "word " * 300)
    plain = message.get_body(("plain",)).get_content()

    assert "..." in plain and len(plain) < 900


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(notify.settings, "POST_NOTIFICATIONS", True)
    monkeypatch.setattr(mailer, "send_message", lambda message: sent.append(message))
    return sent


def test_post_event_sends_when_enabled(outbox):
    assert notify.post_event("o@example.com", "published", page_name="P", text="Hi") is True
    assert len(outbox) == 1


def test_post_event_is_silent_without_recipient_or_when_switched_off(outbox, monkeypatch):
    assert notify.post_event("", "published", text="Hi") is False
    assert notify.post_event(None, "published", text="Hi") is False

    monkeypatch.setattr(notify.settings, "POST_NOTIFICATIONS", False)
    assert notify.post_event("o@example.com", "published", text="Hi") is False

    monkeypatch.setattr(notify.settings, "POST_NOTIFICATIONS", True)
    monkeypatch.setattr(notify.settings, "SMTP_HOST", "")
    assert notify.post_event("o@example.com", "published", text="Hi") is False
    assert outbox == []


def test_a_mail_failure_never_raises(monkeypatch):
    monkeypatch.setattr(notify.settings, "POST_NOTIFICATIONS", True)

    def boom(message):
        raise mailer.ApiError(502, "EMAIL_UNAVAILABLE", "down")

    monkeypatch.setattr(mailer, "send_message", boom)

    assert notify.post_event("o@example.com", "published", text="Hi") is False


# ---------------------------------------------------------------- helpers for the route tests

class Events:
    """Records notifications the routes ask for and every Facebook call they make."""

    def __init__(self, monkeypatch):
        self.notices = []
        self.calls = []
        self.fail_delete_of = None
        self.published_state = True

        monkeypatch.setattr(notify, "post_event", lambda to, event, **kw: self.notices.append((to, event, kw)))

        page = SimpleNamespace(page_id="111", page_name="Lahore Bakery")
        monkeypatch.setattr(facebook, "require_connection", lambda db, user: (page, "TOKEN"))
        monkeypatch.setattr(schedule, "require_connection", lambda db, user: (page, "TOKEN"))
        monkeypatch.setattr(schedule, "get_user_connection", lambda db, user_id: (page, "TOKEN"))
        monkeypatch.setattr(schedule, "token_for_post", lambda db, user_id, post_id: "TOKEN")

        api = schedule.facebook_api
        monkeypatch.setattr(api, "publish_text", self.publish_text)
        monkeypatch.setattr(api, "publish_photo", self.publish_photo)
        monkeypatch.setattr(api, "update_post", self.update_post)
        monkeypatch.setattr(api, "delete_post", self.delete_post)
        monkeypatch.setattr(api, "is_post_published", lambda post_id, token: self.published_state)

    def publish_text(self, page_id, token, message, scheduled_at=None):
        self.calls.append(("publish_text", page_id, message, scheduled_at))
        return {"id": f"{page_id}_new{len(self.calls)}"}

    def publish_photo(self, page_id, token, data, filename, content_type, message, scheduled_at=None):
        self.calls.append(("publish_photo", page_id, message, scheduled_at))
        return {"id": "PH1", "post_id": f"{page_id}_newphoto{len(self.calls)}"}

    def update_post(self, post_id, token, message=None, scheduled_at=None):
        self.calls.append(("update_post", post_id, message, scheduled_at))

    def delete_post(self, post_id, token):
        self.calls.append(("delete_post", post_id))

        if post_id == self.fail_delete_of:
            raise FacebookError(400, {"message": "no", "facebook_response": {"error": {"code": 1}}})

    def names(self):
        return [call[0] for call in self.calls]


@pytest.fixture
def fb(monkeypatch):
    return Events(monkeypatch)


def sign_in(client, login, uid=None):
    who = login(firebase_user(uid=uid))
    client.post("/auth/sync")

    with SessionLocal() as db:
        return db.query(User).filter(User.firebase_uid == who["uid"]).first().id


def add_post(user_id, message="Eid offer", with_image=False, minutes=60 * 24 * 3, status="scheduled", post_id="111_old"):
    with SessionLocal() as db:
        item = ScheduledPost(
            user_id=user_id, message=message, with_image=with_image, status=status,
            run_at=datetime.utcnow() + timedelta(minutes=minutes), facebook_post_id=post_id,
        )
        db.add(item)
        db.commit()
        return str(item.id)


def row_of(post_id):
    with SessionLocal() as db:
        item = db.get(ScheduledPost, uuid.UUID(post_id))
        return SimpleNamespace(message=item.message, with_image=item.with_image, fb=item.facebook_post_id, run_at=item.run_at)


def later(days=5):
    return (datetime.now(timezone.utc) + timedelta(days=days)).isoformat()


# ---------------------------------------------------------------- notifications from the routes

def test_publishing_a_text_post_emails_the_owner(client, login, fb):
    sign_in(client, login)

    response = client.post("/facebook/publish", json={"message": "Summer sale"})

    assert response.status_code == 200, response.text
    (to, event, kw), = fb.notices
    assert event == "published" and to.endswith("@example.com")
    assert kw["text"] == "Summer sale" and kw["page_name"] == "Lahore Bakery"


def test_scheduling_a_post_emails_the_owner(client, login, fb):
    sign_in(client, login)

    response = client.post("/schedule/post", data={"message": "Eid sale", "run_at": later()})

    assert response.status_code == 200, response.text
    (to, event, kw), = fb.notices
    assert event == "scheduled" and kw["text"] == "Eid sale" and kw["when"] is not None


def test_a_failed_publish_sends_no_email(client, login, fb, monkeypatch):
    sign_in(client, login)

    def refuse(*args, **kwargs):
        raise FacebookError(400, {"message": "x", "facebook_response": {"error": {"code": 190}}})

    monkeypatch.setattr(facebook.facebook_api, "publish_text", refuse)

    assert client.post("/facebook/publish", json={"message": "Hi"}).status_code == 401
    assert fb.notices == []


# ---------------------------------------------------------------- editing a scheduled post

def test_edit_text_replaces_the_post_and_keeps_one_copy(client, login, fb):
    user = sign_in(client, login)
    post = add_post(user)

    response = client.put(f"/schedule/{post}", data={"message": "  New wording  "})

    assert response.status_code == 200, response.text
    assert response.json()["changed"] is True
    assert fb.names() == ["publish_text", "delete_post"]
    assert fb.calls[0][1:3] == ("111", "New wording")
    assert fb.calls[1][1] == "111_old"
    saved = row_of(post)
    assert saved.message == "New wording" and saved.fb != "111_old"
    assert [event for _, event, _ in fb.notices] == ["updated"]


def test_edit_time_only(client, login, fb):
    user = sign_in(client, login)
    post = add_post(user)

    response = client.put(f"/schedule/{post}", data={"run_at": later(10)})

    assert response.status_code == 200, response.text
    assert fb.names() == ["publish_text", "delete_post"]
    assert fb.calls[0][3] is not None
    assert row_of(post).message == "Eid offer"


def test_edit_caption_of_a_photo_post_updates_in_place(client, login, fb):
    user = sign_in(client, login)
    post = add_post(user, with_image=True)

    response = client.put(f"/schedule/{post}", data={"message": "Better caption"})

    assert response.status_code == 200, response.text
    assert fb.names() == ["update_post"]
    assert fb.calls[0][1:3] == ("111_old", "Better caption")
    saved = row_of(post)
    assert saved.with_image is True and saved.fb == "111_old"


def test_replacing_the_picture_creates_a_new_post_then_deletes_the_old(client, login, fb):
    user = sign_in(client, login)
    post = add_post(user, with_image=True)

    response = client.put(
        f"/schedule/{post}",
        data={"message": "Same text"},
        files={"image": ("new.png", b"\x89PNG-data", "image/png")},
    )

    assert response.status_code == 200, response.text
    assert fb.names() == ["publish_photo", "delete_post"]
    assert row_of(post).with_image is True


def test_adding_a_picture_to_a_text_post(client, login, fb):
    user = sign_in(client, login)
    post = add_post(user, with_image=False)

    response = client.put(f"/schedule/{post}", files={"image": ("p.png", b"\x89PNG-data", "image/png")})

    assert response.status_code == 200, response.text
    assert fb.names() == ["publish_photo", "delete_post"]
    saved = row_of(post)
    assert saved.with_image is True and saved.message == "Eid offer"


def test_removing_the_picture_makes_it_a_text_post(client, login, fb):
    user = sign_in(client, login)
    post = add_post(user, with_image=True)

    response = client.put(f"/schedule/{post}", data={"remove_image": "true", "message": "Text only now"})

    assert response.status_code == 200, response.text
    assert fb.names() == ["publish_text", "delete_post"]
    assert row_of(post).with_image is False


def test_nothing_changed_makes_no_facebook_call(client, login, fb):
    user = sign_in(client, login)
    post = add_post(user)

    response = client.put(f"/schedule/{post}", data={"message": "Eid offer"})

    assert response.status_code == 200
    assert response.json()["changed"] is False
    assert fb.calls == [] and fb.notices == []


def test_a_post_about_to_go_out_cannot_be_edited(client, login, fb):
    user = sign_in(client, login)
    post = add_post(user, minutes=5)

    response = client.put(f"/schedule/{post}", data={"message": "Late change"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "POST_TOO_CLOSE"
    assert fb.calls == []


def test_an_edit_cannot_empty_the_post(client, login, fb):
    user = sign_in(client, login)
    post = add_post(user)

    response = client.put(f"/schedule/{post}", data={"message": "   "})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "POST_EMPTY"


def test_a_bad_new_time_is_refused(client, login, fb):
    user = sign_in(client, login)
    post = add_post(user)

    soon = (datetime.now(timezone.utc) + timedelta(minutes=2)).isoformat()
    assert client.put(f"/schedule/{post}", data={"run_at": soon}).status_code == 400
    assert fb.calls == []


def test_when_the_old_post_cannot_be_deleted_only_one_copy_remains(client, login, fb):
    user = sign_in(client, login)
    post = add_post(user)
    fb.fail_delete_of = "111_old"

    response = client.put(f"/schedule/{post}", data={"message": "New wording"})

    assert response.status_code >= 400
    names = fb.names()
    assert names[0] == "publish_text" and names.count("delete_post") == 2
    assert fb.calls[-1][1] != "111_old"  # the NEW post was taken back
    saved = row_of(post)
    assert saved.message == "Eid offer" and saved.fb == "111_old"
    assert fb.notices == []


def test_other_users_cannot_edit_my_post(client, login, fb):
    owner = sign_in(client, login, uid="owner-1")
    post = add_post(owner)
    sign_in(client, login, uid="intruder-1")

    response = client.put(f"/schedule/{post}", data={"message": "Hacked"})

    assert response.status_code == 404
    assert fb.calls == [] and row_of(post).message == "Eid offer"


def test_finished_posts_cannot_be_edited(client, login, fb):
    user = sign_in(client, login)
    post = add_post(user, status="published")

    assert client.put(f"/schedule/{post}", data={"message": "x"}).status_code == 404


# ---------------------------------------------------------------- the live check

def test_a_post_that_went_live_is_emailed_once(client, login, fb):
    user = sign_in(client, login)
    add_post(user, minutes=-30, post_id="111_due")

    assert schedule.poll_due_posts() == 1

    (to, event, kw), = fb.notices
    assert event == "live" and kw["post_id"] == "111_due" and kw["page_name"] == "Lahore Bakery"

    assert schedule.poll_due_posts() == 0
    assert len(fb.notices) == 1


def test_a_post_not_live_yet_is_not_announced(client, login, fb):
    user = sign_in(client, login)
    add_post(user, minutes=-30, post_id="111_due")
    fb.published_state = False

    assert schedule.poll_due_posts() == 0
    assert fb.notices == []


def test_opening_the_list_announces_posts_that_just_went_live(client, login, fb):
    user = sign_in(client, login)
    add_post(user, minutes=-30, post_id="111_due")

    data = client.get("/schedule").json()

    assert data["upcoming"] == [] and len(data["past"]) == 1
    assert [event for _, event, _ in fb.notices] == ["live"]

    client.get("/schedule")
    assert len(fb.notices) == 1
