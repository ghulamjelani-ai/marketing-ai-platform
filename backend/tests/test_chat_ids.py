"""Chat conversation ids: valid ones work, broken or foreign ones give a clean 404."""

import pytest

from app.routers import chat
from conftest import firebase_user


@pytest.fixture
def user(client, login, monkeypatch):
    monkeypatch.setattr(chat, "generate_marketing_ai_reply", lambda user_message, **kw: f"Reply to {user_message}")
    monkeypatch.setattr(chat, "update_memory_in_background", lambda *a, **kw: None)
    login(firebase_user(uid="chat-owner"))
    client.post("/auth/sync")


def ask(client, message, conversation_id=None):
    return client.post("/chat/plan", json={"message": message, "conversation_id": conversation_id})


def test_conversation_continues_and_loads(client, user):
    first = ask(client, "I run a bakery").json()
    second = ask(client, "Make an Eid post", first["conversation_id"])

    assert second.status_code == 200
    assert second.json()["conversation_id"] == first["conversation_id"]

    history = client.get(f"/chat/history/{first['conversation_id']}").json()
    assert [m["content"] for m in history["messages"]] == [
        "I run a bakery", "Reply to I run a bakery", "Make an Eid post", "Reply to Make an Eid post",
    ]


@pytest.mark.parametrize("bad_id", ["not-a-uuid", "123", "00000000-0000-0000-0000-000000000000"])
def test_broken_or_unknown_ids_are_404(client, user, bad_id):
    assert client.get(f"/chat/history/{bad_id}").status_code == 404
    assert client.delete(f"/chat/conversations/{bad_id}").status_code == 404
    assert ask(client, "hello", bad_id).status_code == 404


def test_someone_elses_conversation_is_404(client, user, login):
    owners = ask(client, "My private plan").json()["conversation_id"]

    login(firebase_user(uid="someone-else"))
    client.post("/auth/sync")

    assert client.get(f"/chat/history/{owners}").status_code == 404
    assert client.delete(f"/chat/conversations/{owners}").status_code == 404
