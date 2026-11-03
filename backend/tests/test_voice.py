"""The voice button: a short recording in, the spoken words out (OpenAI is faked)."""

from types import SimpleNamespace

import httpx
import pytest
from openai import APIConnectionError, NotFoundError, RateLimitError

from app.core import openai_client
from app.core.config import settings
from conftest import firebase_user

SPEECH = b"\x1aE\xdf\xa3" + b"\x00" * 4000  # looks like a small webm file


class FakeAudio:
    """Stands in for client.audio.transcriptions."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = []
        self.transcriptions = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return SimpleNamespace(text=answer)


@pytest.fixture
def openai(monkeypatch):
    def use(*answers):
        fake = FakeAudio(answers)
        monkeypatch.setattr(openai_client, "_get_client", lambda: SimpleNamespace(audio=fake))
        return fake

    return use


@pytest.fixture
def user(client, login):
    login(firebase_user())
    client.post("/auth/sync")


def send(client, data=SPEECH, content_type="audio/webm;codecs=opus", name="voice.webm"):
    return client.post("/voice/transcribe", files={"audio": (name, data, content_type)})


def error_code(response):
    return response.json()["error"]["code"]


def openai_error(kind):
    request = httpx.Request("POST", "https://api.openai.com/v1/audio/transcriptions")
    if kind is APIConnectionError:
        return APIConnectionError(request=request)
    return kind("error", response=httpx.Response(429 if kind is RateLimitError else 404, request=request), body=None)


def test_speech_becomes_text(client, user, openai):
    fake = openai("  I run a bakery in Lahore, make an Eid offer post  ")

    response = send(client)

    assert response.status_code == 200, response.text
    assert response.json() == {"success": True, "text": "I run a bakery in Lahore, make an Eid offer post"}
    call = fake.calls[0]
    assert call["model"] == settings.transcribe_model_list[0]
    assert call["file"][0] == "voice.webm" and call["file"][2] == "audio/webm"
    assert "hashtags" in call["prompt"]  # marketing words are hinted


def test_urdu_speech(client, user, openai):
    openai("ہماری بیکری میں عید کی خاص پیشکش")

    assert send(client).json()["text"] == "ہماری بیکری میں عید کی خاص پیشکش"


@pytest.mark.parametrize("content_type,name", [("audio/ogg", "v.ogg"), ("audio/mp4", "v.mp4"), ("audio/wav", "v.wav"), ("audio/mpeg", "v.mp3")])
def test_other_browser_formats(client, user, openai, content_type, name):
    fake = openai("hello")

    assert send(client, content_type=content_type, name=name).status_code == 200
    assert fake.calls[0]["file"][0].startswith("voice.")


def test_business_profile_helps_recognition(client, user, openai):
    fake = openai("text")
    client.put("/memory", json={"summary": "Sunrise Bakery in Lahore sells sourdough"})

    send(client)

    assert "Sunrise Bakery" in fake.calls[0]["prompt"]


def test_next_model_is_tried_when_one_fails(client, user, openai):
    fake = openai(openai_error(NotFoundError), "works on the second model")

    response = send(client)

    assert response.json()["text"] == "works on the second model"
    assert [c["model"] for c in fake.calls] == settings.transcribe_model_list[:2]


@pytest.mark.parametrize("error,status,code", [
    (RateLimitError, 429, "AI_RATE_LIMIT"),
    (APIConnectionError, 502, "AI_UNAVAILABLE"),
])
def test_ai_problems_have_clear_errors(client, user, openai, error, status, code):
    openai(*[openai_error(error)] * len(settings.transcribe_model_list))

    response = send(client)

    assert response.status_code == status
    assert error_code(response) == code


def test_silence(client, user, openai):
    openai("   ")

    response = send(client)

    assert response.status_code == 422
    assert error_code(response) == "VOICE_NOT_UNDERSTOOD"


def test_too_short(client, user, openai):
    fake = openai("never used")

    response = send(client, data=b"\x00" * 200)

    assert error_code(response) == "VOICE_TOO_SHORT"
    assert fake.calls == []  # nothing sent to OpenAI


def test_too_long(client, user, openai, monkeypatch):
    fake = openai("never used")
    monkeypatch.setattr("app.routers.voice.MAX_AUDIO_SIZE", 2000)

    response = send(client)

    assert response.status_code == 413
    assert error_code(response) == "VOICE_TOO_LONG"
    assert fake.calls == []


@pytest.mark.parametrize("content_type", ["image/png", "text/plain", "audio/x-unknown", "application/octet-stream"])
def test_not_audio(client, user, openai, content_type):
    fake = openai("never used")

    response = send(client, content_type=content_type)

    assert response.status_code == 400
    assert error_code(response) == "VOICE_BAD_FORMAT"
    assert fake.calls == []


def test_needs_sign_in(client):
    assert send(client).status_code == 401
