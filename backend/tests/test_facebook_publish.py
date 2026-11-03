"""Publishing with a mocked Graph API: error mapping and one-publish-per-key."""

from types import SimpleNamespace

import pytest
import requests

from app.core import facebook_api
from app.routers import facebook
from conftest import firebase_user


class FakeGraph:
    """Stands in for requests.post inside facebook_api; records each call."""

    def __init__(self, monkeypatch):
        self.calls = []
        self.answer = (200, {"id": "PAGE_1"})
        monkeypatch.setattr(facebook_api.requests, "post", self.post)

    def post(self, url, data=None, files=None, timeout=None):
        self.calls.append(url)

        if isinstance(self.answer, Exception):
            raise self.answer

        status, body = self.answer
        return SimpleNamespace(status_code=status, json=lambda: body)


@pytest.fixture
def graph(monkeypatch, login):
    login(firebase_user())
    page = SimpleNamespace(page_id="PAGE")
    monkeypatch.setattr(facebook, "require_connection", lambda db, user: (page, "TOKEN"))
    return FakeGraph(monkeypatch)


def publish(client, key=None, message="Summer sale on running shoes"):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post("/facebook/publish", json={"message": message}, headers=headers)


def graph_error(code, message="boom"):
    return (400, {"error": {"code": code, "message": message}})


def test_publish_once(client, graph):
    response = publish(client)

    assert response.status_code == 200
    assert response.json()["post_id"] == "PAGE_1"
    assert len(graph.calls) == 1


def test_same_key_publishes_only_once(client, graph):
    first = publish(client, key="run-1")
    second = publish(client, key="run-1")

    assert first.status_code == second.status_code == 200
    assert second.json() == first.json()
    assert second.headers["idempotent-replay"] == "true"
    assert len(graph.calls) == 1


def test_different_keys_publish_twice(client, graph):
    publish(client, key="run-1")
    publish(client, key="run-2")

    assert len(graph.calls) == 2


def test_failed_publish_frees_the_key_for_a_retry(client, graph):
    graph.answer = graph_error(1)
    assert publish(client, key="run-1").status_code == 502

    graph.answer = (200, {"id": "PAGE_2"})
    retry = publish(client, key="run-1")

    assert retry.status_code == 200
    assert len(graph.calls) == 2


def test_key_still_running_gets_409(client, graph):
    from app.core import idempotency

    idempotency._entries[("/facebook/publish", "busy")] = {"at": 9e18, "done": False}

    response = publish(client, key="busy")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "ALREADY_RUNNING"
    assert graph.calls == []


@pytest.mark.parametrize(
    "answer,status,code",
    [
        (graph_error(190, "Error validating access token"), 401, "FB_TOKEN_EXPIRED"),
        (graph_error(200, "Permissions error"), 403, "FB_PERMISSION"),
        (graph_error(4, "Application request limit reached"), 429, "FB_RATE_LIMIT"),
        ((500, {"error": {"code": 2, "message": "Service temporarily unavailable"}}), 502, "FB_ERROR"),
    ],
    ids=["401-token-expired", "403-permission", "rate-limit", "500-server"],
)
def test_facebook_errors_are_explained(client, graph, answer, status, code):
    graph.answer = answer

    response = publish(client)

    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_network_failure(client, graph):
    graph.answer = requests.ConnectionError("offline")

    response = publish(client)

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "FB_NETWORK"


def test_empty_message_is_refused(client, graph):
    assert publish(client, message="   ").status_code == 400
    assert graph.calls == []
