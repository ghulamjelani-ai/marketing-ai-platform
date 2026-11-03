"""Rules that decide if an Autopilot topic is real text worth sending to the AI.

The frontend runs the same rules (frontend/src/utils/validateTopic.js), but the
backend never trusts it: every Autopilot request is checked here again.
"""

import re

from app.core.errors import ApiError

MIN_LENGTH = 10
MAX_LENGTH = 500

EXAMPLE = "Please describe your post topic in words, for example: 'Summer sale on running shoes'."

_TAG = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")
_TOKEN = re.compile(r"\S+")
_EDGE_PUNCT = ".,!?;:'\"()[]{}-–—…،۔؟"
_VOWELS = set("aeiouy")
_KEYBOARD_ROWS = ("qwertyuiop", "asdfghjkl", "zxcvbnm", "1234567890")


class TopicError(ApiError):
    def __init__(self, code: str, message: str):
        super().__init__(400, code, message)


def _is_latin(word: str) -> bool:
    return all("a" <= ch <= "z" for ch in word)


def _looks_like_word(word: str) -> bool:
    """True when a lower-case, letters-only token could be a real word."""

    if len(word) < 2:
        return False

    if not _is_latin(word):
        # Urdu and other scripts: accept any alphabetic token of two or more letters.
        return len(set(word)) > 1

    if len(set(word)) == 1:
        return False

    if re.search(r"(.)\1\1", word):
        return False

    if not any(ch in _VOWELS for ch in word):
        return len(word) <= 3  # short forms such as "dr", "st", "mr"

    if re.search(r"[^aeiouy]{5,}", word):
        return False

    if len(word) >= 4 and any(word in row for row in _KEYBOARD_ROWS):
        return False

    if len(word) >= 7:
        vowels = sum(ch in _VOWELS for ch in word)

        if vowels / len(word) < 0.25:
            return False

    return True


def validate_topic(raw: str | None) -> str:
    """Returns the cleaned topic or raises TopicError with a code and a friendly message."""

    text = " ".join((raw or "").split())

    if not text:
        raise TopicError("TOPIC_EMPTY", "Tell Autopilot what the post is about. " + EXAMPLE)

    if len(text) < MIN_LENGTH:
        raise TopicError("TOPIC_TOO_SHORT", f"The topic is too short (at least {MIN_LENGTH} characters). " + EXAMPLE)

    if len(text) > MAX_LENGTH:
        raise TopicError("TOPIC_TOO_LONG", f"The topic is too long (at most {MAX_LENGTH} characters).")

    if _TAG.search(text):
        raise TopicError("TOPIC_HAS_HTML", "HTML or script tags are not allowed. " + EXAMPLE)

    if not any(ch.isalpha() for ch in text):
        raise TopicError("TOPIC_NO_WORDS", "The topic has no words, only numbers, symbols or emoji. " + EXAMPLE)

    letters = [ch.lower() for ch in text if ch.isalnum()]

    if len(set(letters)) <= 2:
        raise TopicError("TOPIC_REPEATED", "The topic is just repeated characters. " + EXAMPLE)

    lettered = []

    for token in _TOKEN.findall(text):
        token = token.strip(_EDGE_PUNCT).lower()

        if any(ch.isalpha() for ch in token):
            lettered.append(token)

    words = [token for token in lettered if token.isalpha() and _looks_like_word(token)]

    if len(words) < 2 or len(words) * 2 < len(lettered):
        raise TopicError("TOPIC_GIBBERISH", "That does not look like real words. " + EXAMPLE)

    return text
