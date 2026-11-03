"""POST /autopilot/post: input checks, the AI intent check and the structured post."""

import json
from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, RateLimitError

from app.core import openai_client
from app.routers import autopilot
from conftest import firebase_user

GARBAGE = [
    "",
    "   ",
    "123456",
    "1234563qrguoherjgnvsui",
    "!!!???",
    "aaaaaaaaaa",
    "asdfghjkl",
    "<script>alert(1)</script>",
    "😀😀😀😀😀😀😀😀😀😀😀",
    "x" * 5000,
]

GOOD_POST = {
    "caption": "Summer sale on running shoes! Shop today.",
    "description": "Up to 30% off all running shoes this week.",
    "hashtags": ["#SummerSale", "#RunningShoes", "#Fitness"],
    "image_prompt": "Running shoes on a sunny track, bright morning light.",
    "language": "English",
}


class FakeOpenAI:
    """Answers chat calls from a queue: dicts become JSON, strings are sent as-is,
    exceptions are raised. Records every call."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        answer = self.answers.pop(0)

        if isinstance(answer, Exception):
            raise answer

        content = answer if isinstance(answer, str) else json.dumps(answer)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


@pytest.fixture
def fake_ai(monkeypatch):
    def install(*answers):
        fake = FakeOpenAI(answers)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=fake.create)))
        monkeypatch.setattr(openai_client, "_get_client", lambda: client)
        # The memory refresh after a post is another AI call; it is not under test here.
        monkeypatch.setattr(autopilot, "update_memory_in_background", lambda *args: None)
        return fake

    return install


@pytest.fixture
def user(login):
    return login(firebase_user())


def post(client, text):
    return client.post("/autopilot/post", json={"request": text})


@pytest.mark.parametrize("text", GARBAGE, ids=[repr(t[:15]) for t in GARBAGE])
def test_garbage_is_rejected_before_any_ai_call(client, user, fake_ai, text):
    fake = fake_ai()  # no answers: any AI call would fail the test

    response = post(client, text)

    assert response.status_code == 400
    body = response.json()
    assert set(body) == {"error"}
    assert body["error"]["code"].startswith("TOPIC_")
    assert body["error"]["message"]
    assert fake.calls == []


def test_ai_intent_check_can_stop_the_post(client, user, fake_ai):
    fake = fake_ai({"valid": False, "reason": "This is placeholder text"})

    response = post(client, "Lorem ipsum dolor sit amet")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TOPIC_UNCLEAR"
    assert "placeholder text" in response.json()["error"]["message"]
    assert len(fake.calls) == 1  # only the cheap check, no post was written


def test_valid_topic_returns_typed_post(client, user, fake_ai):
    fake = fake_ai({"valid": True, "reason": "ok"}, GOOD_POST)

    response = post(client, "  Summer sale on running shoes  ")

    assert response.status_code == 200
    assert response.json()["post"] == GOOD_POST
    writer_call = fake.calls[1]
    assert writer_call["response_format"]["type"] == "json_schema"
    assert "Request: Summer sale on running shoes" in writer_call["messages"][1]["content"]


def test_urdu_topic_passes(client, user, fake_ai):
    fake_ai({"valid": True, "reason": "ok"}, {**GOOD_POST, "language": "Urdu"})

    response = post(client, "ہماری نئی بیکری کا افتتاح جمعہ کو ہے")

    assert response.status_code == 200
    assert response.json()["post"]["language"] == "Urdu"


def test_malformed_json_is_retried(client, user, fake_ai):
    fake = fake_ai({"valid": True, "reason": "ok"}, "{not json", GOOD_POST)

    response = post(client, "Grand opening of our new cafe in Lahore this Friday")

    assert response.status_code == 200
    assert len(fake.calls) == 3


def test_missing_fields_are_retried(client, user, fake_ai):
    missing = {k: v for k, v in GOOD_POST.items() if k != "hashtags"}
    fake = fake_ai({"valid": True, "reason": "ok"}, missing, GOOD_POST)

    assert post(client, "Summer sale on running shoes").status_code == 200
    assert len(fake.calls) == 3


def test_extra_fields_are_dropped(client, user, fake_ai):
    fake_ai({"valid": True, "reason": "ok"}, {**GOOD_POST, "secret": "x", "html": "<b>"})

    response = post(client, "Summer sale on running shoes")

    assert response.status_code == 200
    assert set(response.json()["post"]) == set(GOOD_POST)


@pytest.mark.parametrize("tags", [["#a", "#b"], [f"#t{i}" for i in range(9)]])
def test_hashtag_count_is_enforced(client, user, fake_ai, tags):
    fake = fake_ai({"valid": True, "reason": "ok"}, *[{**GOOD_POST, "hashtags": tags}] * 3)

    response = post(client, "Summer sale on running shoes")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_BAD_OUTPUT"
    assert len(fake.calls) == 4  # check + first try + 2 retries


def test_hashtags_are_normalised(client, user, fake_ai):
    fake_ai({"valid": True, "reason": "ok"}, {**GOOD_POST, "hashtags": ["sale", "#Shoes", "run fast", "sale"]})

    response = post(client, "Summer sale on running shoes")

    assert response.json()["post"]["hashtags"] == ["#sale", "#Shoes", "#runfast"]


def test_gives_up_after_two_retries(client, user, fake_ai):
    fake = fake_ai({"valid": True, "reason": "ok"}, "", "{}", "[1,2]")

    response = post(client, "Summer sale on running shoes")

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "AI_BAD_OUTPUT"
    assert len(fake.calls) == 4


def _request():
    return httpx.Request("POST", "https://api.openai.com/v1/chat/completions")


@pytest.mark.parametrize(
    "error,status,code",
    [
        (APITimeoutError(request=_request()), 504, "AI_TIMEOUT"),
        (APIConnectionError(request=_request()), 502, "AI_UNAVAILABLE"),
        (
            RateLimitError("slow down", response=httpx.Response(429, request=_request()), body=None),
            429,
            "AI_RATE_LIMIT",
        ),
    ],
    ids=["timeout", "ai-down", "rate-limit"],
)
def test_ai_failures_become_clear_errors(client, user, fake_ai, monkeypatch, error, status, code):
    monkeypatch.setattr(openai_client.settings, "OPENAI_MODELS", "")
    fake_ai(error)

    response = post(client, "Summer sale on running shoes")

    assert response.status_code == status
    assert response.json()["error"]["code"] == code


def test_broken_intent_check_does_not_let_the_topic_through(client, user, fake_ai):
    fake = fake_ai("not json at all")

    response = post(client, "Summer sale on running shoes")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "TOPIC_UNCLEAR"
    assert len(fake.calls) == 1


def test_requires_login(client):
    assert post(client, "Summer sale on running shoes").status_code == 401
