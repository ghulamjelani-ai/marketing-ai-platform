import pytest

from app.core.topic_check import TopicError, validate_topic

INVALID = {
    "": "TOPIC_EMPTY",
    "   ": "TOPIC_EMPTY",
    "123456": "TOPIC_TOO_SHORT",
    "1234563qrguoherjgnvsui": "TOPIC_GIBBERISH",
    "!!!???": "TOPIC_TOO_SHORT",
    "!!!???!!!???": "TOPIC_NO_WORDS",
    "1234567890123": "TOPIC_NO_WORDS",
    "aaaaaaaaaa": "TOPIC_REPEATED",
    "abababababab": "TOPIC_REPEATED",
    "asdfghjkl": "TOPIC_TOO_SHORT",
    "asdfghjkl qwertyuiop": "TOPIC_GIBBERISH",
    "asdf qwer zxcv": "TOPIC_GIBBERISH",
    "hjkdf sdfkj lorem": "TOPIC_GIBBERISH",
    "<script>alert(1)</script>": "TOPIC_HAS_HTML",
    "Sale on <b>shoes</b> today": "TOPIC_HAS_HTML",
    "😀😀😀😀😀😀😀😀😀😀😀": "TOPIC_NO_WORDS",
    "🎉🔥💯🎉🔥💯🎉🔥💯🎉": "TOPIC_NO_WORDS",
    "x" * 5000: "TOPIC_TOO_LONG",
}

VALID = [
    "Summer sale on running shoes",
    "Grand opening of our new cafe in Lahore this Friday",
    "ہماری نئی بیکری کا افتتاح جمعہ کو ہے",
    "   Summer sale on running shoes   ",
    "SUMMER sale ON Running SHOES",
    "50% off on all cakes this weekend",
    "Robert'); DROP TABLE users;-- sale on shoes",
    "' OR 1=1 -- weekend discount on pizza",
    "Supercalifragilisticexpialidocious sale this weekend",
    "New iPhone15 cases available now",
    "Eid sale on clothes 🎉",
]


@pytest.mark.parametrize("text,code", INVALID.items(), ids=[repr(k[:20]) for k in INVALID])
def test_rejects_invalid_topics(text, code):
    with pytest.raises(TopicError) as caught:
        validate_topic(text)

    assert caught.value.code == code
    assert caught.value.status_code == 400
    assert caught.value.message


@pytest.mark.parametrize("text", VALID)
def test_accepts_real_topics(text):
    assert validate_topic(text) == " ".join(text.split())


def test_trims_and_collapses_spaces():
    assert validate_topic("  Summer   sale\n on shoes  ") == "Summer sale on shoes"


def test_length_limits_count_after_trimming():
    assert validate_topic("  Fresh bread  ".ljust(30)) == "Fresh bread"

    with pytest.raises(TopicError):
        validate_topic("   ab cd   ")  # 5 characters once trimmed

    assert validate_topic(("Fresh bread " * 50)[:500])

    with pytest.raises(TopicError) as caught:
        validate_topic("Fresh bread " * 50)

    assert caught.value.code == "TOPIC_TOO_LONG"


def test_one_very_long_word_is_rejected():
    with pytest.raises(TopicError):
        validate_topic("sale " + "a" * 300)
