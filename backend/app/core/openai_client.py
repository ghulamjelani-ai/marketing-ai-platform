import base64
import json

from fastapi import HTTPException, status
from pydantic import BaseModel, Field, ValidationError, field_validator
from openai import (
    APIConnectionError,
    APIError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    OpenAI,
    RateLimitError,
)

from app.core.config import settings
from app.core.errors import ApiError


SYSTEM_PROMPT = """
You are a professional AI marketing strategist and copywriter for small businesses
on Facebook.

Always do what the user's LATEST message asks. If earlier messages in the chat were
about something else, ignore them. If the latest message is about a different
business or topic than earlier messages, follow the latest message only and do not
mix the earlier business into it. A saved business profile may follow at the end of
these instructions: treat it as known facts and never ask for it again.

Decide which one of these four cases applies to the latest message.

CASE 1 - Nothing to work with.
Only a bare greeting, or a wish that says nothing about any business, product or
service (for example "hi" or "I want marketing"). Reply in two to four friendly
sentences asking what the business sells or offers, which city or area it serves and
what the main goal is, and end with one short example answer. Use this case only when
the message cannot be used at all. A message that names what is sold or done, even in
a few words, is never CASE 1, and a request to write a post is never CASE 1.

CASE 2 - A marketing plan.
The user describes a business, even in one short line such as "I sell shoes online"
or "I own a gym", or asks for a plan, strategy or campaign. Never ask questions here.
If a detail such as the city or the goal is missing, make a sensible assumption and
write it as a fact. Answer in exactly this format:

1. Business Understanding
2. Target Audience
3. Marketing Strategy
4. Weekly Facebook Content Plan
5. 3 Ready-to-Use Facebook Posts
6. 3 Image Generation Prompts
7. Next Step

In section 5 give every post three parts, each on its own line:
Caption: the text people read first.
Description: one or two sentences with more detail about the offer or product.
Hashtags: five relevant hashtags, mixing local and industry hashtags.
Write section 5 as Post 1, Post 2 and Post 3.

CASE 3 - A post.
The user asks for a post, caption, offer, announcement, ad, promotion or similar,
for example "make a post for our Eid sale" or "a limited time offer for filers and
non filers". Never ask questions first. Write one short line saying what the posts
are for, then give three different post options in exactly this format:

Post 1
Caption: ...
Description: ...
Hashtags: ...
Image prompt: ...

then Post 2 and Post 3 the same way. Always include all four lines for every post,
including the Image prompt line, even when the user only mentioned a caption. The caption is one or two engaging sentences
with a clear call to action, the description is one or two sentences of detail, the
hashtags are five relevant ones, and the image prompt is one detailed sentence
describing a realistic photograph for the post (subject, setting, lighting and
mood). If a word or topic in the request is unclear,
choose the most likely meaning from the context, the user's country and the saved
profile, and state your interpretation in the first line. If the business is
unknown, write posts that fit the request and still sound like a real business.

CASE 4 - A follow-up.
A change request or a question about something already written (for example "make
caption 2 shorter" or "suggest hashtags"). Answer directly and briefly using the
earlier messages. Do not repeat a full plan.

Rules:
- Every section and post must contain real, specific content. Never write
  placeholder text such as "will be determined", "provided later" or "once you
  share".
- Use simple, warm business language.
- Tailor everything to the business, its location and its industry.
- If no business name is given, say "your business" and never invent a name.
- Hashtags must be real, usable hashtags. Never write placeholders such as
  #YourCity, #YourBusiness or #YourBrand: if the city or name is unknown, use
  general hashtags about the topic instead.
- Describe images in a refined beige and maroon palette when it fits naturally.
- Format: plain text only. Never use markdown symbols such as **, __, # or backticks.
  Put each heading on its own line, put short points on their own lines starting
  with "- ", and keep each point to one or two sentences so the reply is easy to scan.
"""


def _get_client() -> OpenAI:
    if not settings.OPENAI_API_KEY:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "OPENAI_API_KEY is missing in the backend .env file",
                "fix": "Add OPENAI_API_KEY=your_key and OPENAI_MODEL=model_name to backend/.env and restart the backend.",
            },
        )

    if not settings.OPENAI_MODEL:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "message": "OPENAI_MODEL is missing in the backend .env file",
                "fix": "Add OPENAI_MODEL=model_name to backend/.env and restart the backend.",
            },
        )

    # Ask for gzip/deflate only: some installed HTTP library versions fail to
    # decode brotli/zstd responses and the request crashes with a TypeError.
    return OpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=60.0,
        default_headers={"Accept-Encoding": "gzip, deflate"},
    )


NL = chr(10)


def _system_text(memory: str | None) -> str:
    text = SYSTEM_PROMPT.strip()

    if memory and memory.strip():
        text += (
            NL + NL
            + "Saved profile of this user's business (from earlier chats; treat it as "
            + "known and do not ask for it again):" + NL
            + memory.strip()
        )

    return text


def _try_models(models: list[str], call):
    """Calls call(model) for each model in turn and returns the first success.

    A bad API key fails every model, so it is raised at once. Any other OpenAI error
    (retired model, quota, timeout, server error) moves on to the next model. When all
    models fail, the last error is raised so the normal error messages still apply.
    """

    last_error = None

    for model in models:
        try:
            return call(model)
        except AuthenticationError:
            raise
        except APIError as exc:
            print(f"OpenAI model {model} failed, trying the next one:", repr(exc))
            last_error = exc

    raise last_error


def _chat_create(client: OpenAI, **kwargs):
    """chat.completions.create with the fallback list of chat models."""

    return _try_models(
        settings.chat_model_list,
        lambda model: client.chat.completions.create(model=model, **kwargs),
    )


def _openai_errors(call):
    """Run an OpenAI call and turn provider errors into clear, coded API errors."""

    try:
        return call()
    except AuthenticationError:
        raise ApiError(502, "AI_KEY_REJECTED", "The OpenAI API key was rejected. Check OPENAI_API_KEY in backend/.env.")
    except RateLimitError:
        raise ApiError(429, "AI_RATE_LIMIT", "The AI service is busy or the quota is used up. Please wait a minute and try again.")
    except BadRequestError:
        raise ApiError(400, "AI_BAD_REQUEST", "The AI could not process this request. Try again, or try different wording.")
    except APITimeoutError:
        raise ApiError(504, "AI_TIMEOUT", "The AI took too long to answer. Please try again.")
    except APIConnectionError:
        raise ApiError(502, "AI_UNAVAILABLE", "Could not reach the AI service. Check the internet connection and try again.")
    except APIStatusError as exc:
        raise ApiError(502, "AI_ERROR", f"The AI service returned an error (status {exc.status_code}). Please try again.")

# ---------------------------------------------------------------------------
# Speech to text (the voice button)
# ---------------------------------------------------------------------------

# Words the recogniser should expect, so marketing terms are spelled right.
VOICE_HINT = (
    "A small business owner talks to a marketing assistant about Facebook posts, captions, "
    "hashtags, offers, discounts, Eid, Ramadan, Lahore, Karachi, Islamabad. "
    "They may speak English, Urdu or a mix of both."
)


def transcribe_audio(audio: bytes, filename: str, content_type: str, memory: str | None = None) -> str:
    """Turns a short voice recording into text. The language is detected automatically."""

    client = _get_client()
    hint = VOICE_HINT + (" Business: " + memory.strip()[:300] if memory and memory.strip() else "")

    result = _openai_errors(
        lambda: _try_models(
            settings.transcribe_model_list,
            lambda model: client.audio.transcriptions.create(
                model=model,
                file=(filename, audio, content_type),
                prompt=hint,
            ),
        )
    )

    return (getattr(result, "text", "") or "").strip()


def generate_marketing_ai_reply(
    user_message: str,
    business_name: str = "your business",
    industry: str | None = None,
    history: list[dict] | None = None,
    memory: str | None = None,
) -> str:
    client = _get_client()

    # The frontend sends the placeholder "My Business" when no name is known.
    if not business_name or business_name.strip().lower() in ("my business", "your business"):
        business_name = "Not provided"

    user_prompt = (
        f"Business Name: {business_name}\n"
        f"Industry: {industry or 'Not specified'}\n\n"
        f"User Message:\n{user_message}"
    )

    try:
        completion = _chat_create(
            client,
            messages=[
                {"role": "system", "content": _system_text(memory)},
                *(history or []),
                {"role": "user", "content": user_prompt},
            ],
        )
    except AuthenticationError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The OpenAI API key was rejected. Check OPENAI_API_KEY in backend/.env.",
        )
    except RateLimitError:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="OpenAI rate limit or quota reached. Check your OpenAI billing and try again.",
        )
    except APIConnectionError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach the OpenAI service. Check the internet connection.",
        )
    except APIStatusError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"OpenAI returned an error (status {exc.status_code}).",
        )

    reply = completion.choices[0].message.content

    if not reply:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI returned an empty reply. Please try again.",
        )

    return reply



# ---------------------------------------------------------------------------
# Image generation (used by the images router and by scheduled posts)
# ---------------------------------------------------------------------------

IMAGE_STYLE_SUFFIX = (
    " Professional commercial photograph, natural light, sharp focus, rich detail, "
    "clean composition for a square feed image, warm beige and deep maroon accents, "
    "with one short, perfectly spelled headline in clean bold typography, no logos, no watermark."
)

ENHANCE_PROMPT = """
You are an art director for a small business's Facebook posts. Rewrite the image idea
below into one rich prompt for a text-to-image model.

- Make it a realistic, high-end commercial photograph unless the idea clearly asks for
  an illustration.
- In 60 to 90 words describe the main subject, the setting, the lighting, the camera
  view and lens, the composition for a square feed image, and the mood.
- Use a refined palette of warm beige, soft cream and deep maroon accents when it fits
  naturally.
- Write it so the photo looks real: natural skin and fabric texture, believable
  proportions, no plastic or cartoon look, no distorted hands or faces.
- Add one short headline of 2 to 5 words that fits the idea and the offer (for example
  "Limited Time Offer" or "File Your Taxes Today"). Put the exact words in double
  quotes and describe it as clean, bold, perfectly spelled typography placed on a
  calm area of the photo with strong contrast and generous margins. Use only that
  headline, no other text, and no logos, watermarks or small print.
- Keep the meaning of the idea.
- Return only the prompt.
"""


def enhance_image_prompt(idea: str, memory: str | None = None) -> str:
    """Turns a short idea into a detailed prompt. Falls back to a style suffix on any error."""

    try:
        client = _get_client()

        content = "Image idea: " + idea.strip()

        if memory and memory.strip():
            content += NL + NL + "Business profile: " + memory.strip()

        completion = _chat_create(
            client,
            messages=[
                {"role": "system", "content": ENHANCE_PROMPT.strip()},
                {"role": "user", "content": content},
            ],
        )

        text = (completion.choices[0].message.content or "").strip()

        if len(text) >= 40:
            return text[:1500]
    except Exception as exc:
        print("Image prompt enhancement skipped:", repr(exc))

    return idea.strip() + IMAGE_STYLE_SUFFIX


def generate_image_png(prompt: str, memory: str | None = None, enhance: bool = True) -> bytes:
    final_prompt = enhance_image_prompt(prompt, memory) if enhance else prompt.strip()

    # High quality images can take longer than a chat reply, so this call waits longer.
    client = _get_client().with_options(timeout=180.0)

    # If one image model fails (retired, quota, timeout), the next one in the list is tried.
    result = _openai_errors(
        lambda: _try_models(
            settings.image_model_list,
            lambda model: client.images.generate(
                model=model,
                prompt=final_prompt,
                size="1024x1024",
                quality=settings.OPENAI_IMAGE_QUALITY,
                n=1,
            ),
        )
    )

    image_b64 = result.data[0].b64_json if result.data else None

    if not image_b64:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenAI did not return an image. Please try again.",
        )

    return base64.b64decode(image_b64)


# ---------------------------------------------------------------------------
# Memory: a short profile of the user's business
# ---------------------------------------------------------------------------

MEMORY_PROMPT = """
You keep a short profile of a user's business for a marketing assistant.
You get the current profile and the user's latest message. Return the updated profile.

- Keep only lasting facts that the user stated: business name, what it sells or does,
  city or area, target customers, tone or style, goals and offers.
- Write two to six short plain sentences, at most 120 words.
- Never add facts the user did not state, and never guess.
- If the latest message has no new lasting facts about the business, return the
  current profile unchanged. If there is no profile and no business facts, return nothing.
- Return only the profile text.
"""


def update_memory_summary(current: str | None, user_message: str) -> str:
    client = _get_client()

    shown = (current or "").strip() or "(none)"

    completion = _openai_errors(
        lambda: _chat_create(
            client,
            messages=[
                {"role": "system", "content": MEMORY_PROMPT.strip()},
                {
                    "role": "user",
                    "content": (
                        "Current profile:" + NL + shown + NL + NL
                        + "Latest user message:" + NL + user_message
                    ),
                },
            ],
        )
    )

    text = (completion.choices[0].message.content or "").strip()

    if text == "(none)":
        text = ""

    return text[:900]


# ---------------------------------------------------------------------------
# A week of ready-to-schedule posts
# ---------------------------------------------------------------------------

def draft_week_plan(description: str, memory: str | None, days: int = 7) -> list[dict]:
    client = _get_client()

    shape = (
        '{"posts": [{"caption": "...", "description": "...", '
        '"hashtags": "#a #b #c #d #e", "image_prompt": "..."}]}'
    )

    system = (
        f"You are a social media strategist. Write {days} different Facebook posts for the "
        "business below, one for each day. Vary the theme through the week (for example a "
        "product highlight, behind the scenes, a customer story, an offer and a useful tip). "
        "Use real, specific content and never placeholders. "
        f"Answer only with JSON in this exact shape: {shape} with exactly {days} items. "
        "The caption is one or two engaging sentences, the description is one or two "
        "sentences with more detail, the hashtags are five real, usable hashtags in one string "
        "(never placeholders such as #YourCity or #YourBusiness), "
        "and the image_prompt is one clear sentence for a text-to-image model in a beige "
        "and maroon classic premium style. Write in the language of the business description."
    )

    info = []

    if memory and memory.strip():
        info.append("Saved business profile: " + memory.strip())

    if description and description.strip():
        info.append("Latest description from the user: " + description.strip())

    completion = _openai_errors(
        lambda: _chat_create(
            client,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": (NL + NL).join(info)},
            ],
        )
    )

    try:
        data = json.loads(completion.choices[0].message.content or "{}")
        raw_posts = data["posts"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI did not return a usable plan. Please try again.",
        )

    posts = []

    for item in raw_posts:
        if not isinstance(item, dict) or not str(item.get("caption", "")).strip():
            continue

        hashtags = item.get("hashtags", "")

        if isinstance(hashtags, list):
            hashtags = " ".join(str(tag) for tag in hashtags)

        posts.append(
            {
                "caption": str(item.get("caption", "")).strip(),
                "description": str(item.get("description", "")).strip(),
                "hashtags": str(hashtags).strip(),
                "image_prompt": str(item.get("image_prompt", "")).strip(),
            }
        )

    if len(posts) < days:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI returned an incomplete plan. Please try again.",
        )

    return posts[:days]


# ---------------------------------------------------------------------------
# Suggested posting times (a starting point, not measured data)
# ---------------------------------------------------------------------------

def suggest_post_times(memory: str | None) -> list[dict]:
    client = _get_client()

    shape = '{"times": [{"time": "HH:MM", "reason": "..."}]}'

    system = (
        "You suggest good times of day to publish Facebook posts for a small business, "
        "based on the daily routine of its customers. "
        f"Answer only with JSON in this exact shape: {shape} with exactly 3 items, "
        "in 24-hour local time of the business, spread over the day. "
        "Each reason is one short sentence about what the customers are doing at that time. "
        "Never quote statistics or percentages and never say the times are proven. "
        "If no business is described, suggest general times."
    )

    completion = _openai_errors(
        lambda: _chat_create(
            client,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": (memory or "").strip() or "No business described."},
            ],
        )
    )

    try:
        raw = json.loads(completion.choices[0].message.content or "{}")["times"]
    except (ValueError, KeyError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI did not return usable times.",
        )

    times = []

    for item in raw:
        value = str(item.get("time", "")).strip() if isinstance(item, dict) else ""
        parts = value.split(":")

        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit() and int(parts[0]) < 24 and int(parts[1]) < 60:
            times.append(
                {
                    "time": f"{int(parts[0]):02d}:{int(parts[1]):02d}",
                    "reason": str(item.get("reason", "")).strip(),
                }
            )

    if not times:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The AI did not return usable times.",
        )

    return times[:3]


# ---------------------------------------------------------------------------
# One ready-to-publish post (used by the one-click Autopilot)
# ---------------------------------------------------------------------------

class AutopilotPost(BaseModel):
    """The only shape Autopilot accepts from the model. Extra keys are ignored."""

    caption: str = Field(min_length=1, max_length=400)
    description: str = Field(default="", max_length=800)
    hashtags: list[str] = Field(min_length=3, max_length=8)
    image_prompt: str = Field(min_length=10, max_length=1200)
    language: str = Field(min_length=2, max_length=40)

    @field_validator("caption", "description", "image_prompt", "language", mode="before")
    @classmethod
    def _strip(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("hashtags")
    @classmethod
    def _clean_tags(cls, tags: list[str]) -> list[str]:
        cleaned = []

        for tag in tags:
            tag = "#" + tag.strip().lstrip("#").replace(" ", "")

            if len(tag) < 2:
                raise ValueError("empty hashtag")

            if tag not in cleaned:
                cleaned.append(tag)

        if len(cleaned) < 3:
            raise ValueError("at least 3 different hashtags are needed")

        return cleaned


AUTOPILOT_POST_SCHEMA = {
    "name": "autopilot_post",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "caption": {"type": "string"},
            "description": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
            "image_prompt": {"type": "string"},
            "language": {"type": "string"},
        },
        "required": ["caption", "description", "hashtags", "image_prompt", "language"],
        "additionalProperties": False,
    },
}

POST_RETRIES = 2  # extra attempts after the first one when the output is malformed


def parse_autopilot_post(content: str | None) -> dict:
    """Validates raw model output. Raises ValueError (or ValidationError) when unusable."""

    return AutopilotPost.model_validate(json.loads(content or "")).model_dump()


def draft_single_post(request: str, memory: str | None) -> dict:
    client = _get_client()

    system = (
        "You are a copywriter for small businesses on Facebook. Write ONE ready-to-publish "
        "post that does exactly what the request asks, using the saved business profile "
        "when there is one. Never ask questions. If the business is unknown, write a post "
        "that fits the request and still sounds like a real business. "
        "Answer only with JSON matching the given schema. "
        "caption: one or two engaging sentences with a clear call to action (at most 300 characters). "
        "description: one or two sentences with more detail (at most 600 characters). "
        "hashtags: 3 to 8 real, usable hashtags, each starting with # (never placeholders "
        "such as #YourCity or #YourBusiness). "
        "image_prompt: one detailed sentence describing a realistic photograph for the post "
        "(subject, setting, lighting, mood) with no text in the picture. "
        "language: the name of the language the post is written in. "
        "Write in the language of the request."
    )

    info = []

    if memory and memory.strip():
        info.append("Saved business profile: " + memory.strip())

    info.append("Request: " + request.strip())

    for attempt in range(POST_RETRIES + 1):
        completion = _openai_errors(
            lambda: _chat_create(
                client,
                response_format={"type": "json_schema", "json_schema": AUTOPILOT_POST_SCHEMA},
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": (NL + NL).join(info)},
                ],
            )
        )

        try:
            return parse_autopilot_post(completion.choices[0].message.content)
        except (ValueError, ValidationError) as exc:
            print(f"Autopilot post attempt {attempt + 1} was not usable:", type(exc).__name__)

    raise ApiError(
        status.HTTP_502_BAD_GATEWAY,
        "AI_BAD_OUTPUT",
        "The AI did not return a usable post after several tries. Please try again in a moment.",
    )


TOPIC_CHECK_PROMPT = """
You check topics that a small business owner typed for a Facebook post, before any post
is written. Decide if the text describes something a business could post about: a
product, service, offer, event, announcement, greeting or similar, in any language.
Short and informal topics are fine. Reject text that is random characters, keyboard
mashing, a meaningless mix of letters and numbers, a test string, or that asks for
something other than a marketing post. Never guess a topic for meaningless text.
Answer with JSON only: {"valid": true or false, "reason": "one short sentence for the user"}.
"""

TOPIC_CHECK_SCHEMA = {
    "name": "topic_check",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "valid": {"type": "boolean"},
            "reason": {"type": "string"},
        },
        "required": ["valid", "reason"],
        "additionalProperties": False,
    },
}


def check_topic_intent(topic: str) -> dict:
    """Cheap AI check that a topic means something. Returns {"valid": bool, "reason": str}."""

    client = _get_client()

    completion = _openai_errors(
        lambda: _chat_create(
            client,
            response_format={"type": "json_schema", "json_schema": TOPIC_CHECK_SCHEMA},
            max_tokens=80,
            temperature=0,
            messages=[
                {"role": "system", "content": TOPIC_CHECK_PROMPT.strip()},
                {"role": "user", "content": topic},
            ],
        )
    )

    try:
        data = json.loads(completion.choices[0].message.content or "{}")
        return {"valid": data["valid"] is True, "reason": str(data.get("reason", "")).strip()}
    except (ValueError, KeyError, TypeError):
        # If the check itself fails, do not let the topic through.
        return {"valid": False, "reason": ""}
