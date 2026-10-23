"""Small client for the Facebook Graph API calls used by the app."""

import calendar
import json
from datetime import datetime

import requests

GRAPH_VERSION = "v23.0"
GRAPH_URL = f"https://graph.facebook.com/{GRAPH_VERSION}"


class FacebookError(Exception):
    """A failed Facebook call. `status` is the HTTP status the API should answer with."""

    def __init__(self, status: int, detail):
        super().__init__(str(detail))
        self.status = status
        self.detail = detail


def _unix(moment: datetime) -> int:
    # `moment` is a naive UTC datetime
    return calendar.timegm(moment.timetuple())


def _json(response: requests.Response, invalid_message: str) -> dict:
    try:
        return response.json()
    except ValueError:
        raise FacebookError(502, invalid_message)


def _post(url: str, data: dict, failure: str, files=None, timeout: int = 30) -> dict:
    try:
        response = requests.post(url, data=data, files=files, timeout=timeout)
    except requests.RequestException as exc:
        raise FacebookError(502, f"{failure} request failed: {str(exc)}")

    result = _json(response, "Invalid response received from Facebook")

    if response.status_code != 200:
        raise FacebookError(400, {"message": f"{failure} failed", "facebook_response": result})

    return result


def publish_text(page_id: str, token: str, message: str, scheduled_at: datetime | None = None) -> dict:
    data = {"message": message, "access_token": token}

    if scheduled_at is not None:
        # published must be false, otherwise Facebook publishes at once and ignores the time
        data["published"] = "false"
        data["scheduled_publish_time"] = str(_unix(scheduled_at))
        data["unpublished_content_type"] = "SCHEDULED"

    return _post(f"{GRAPH_URL}/{page_id}/feed", data, "Facebook publishing")


def publish_photo(
    page_id: str,
    token: str,
    image_bytes: bytes,
    filename: str,
    content_type: str,
    message: str,
    scheduled_at: datetime | None = None,
) -> dict:
    files = {"source": (filename or "facebook-image.jpg", image_bytes, content_type)}

    if scheduled_at is None:
        data = {"access_token": token, "published": "true"}

        if message.strip():
            data["caption"] = message.strip()

        return _post(f"{GRAPH_URL}/{page_id}/photos", data, "Facebook photo publishing", files=files, timeout=60)

    # Scheduled photo post (the two steps documented by Meta):
    # 1) upload the photo as an unpublished, temporary photo (it cannot carry a schedule time)
    upload = _post(
        f"{GRAPH_URL}/{page_id}/photos",
        {"access_token": token, "published": "false", "temporary": "true"},
        "Facebook photo upload",
        files=files,
        timeout=60,
    )

    photo_id = upload.get("id")

    if not photo_id:
        raise FacebookError(502, "Facebook did not return a photo id")

    # 2) create the scheduled post that attaches the photo
    data = {
        "access_token": token,
        "published": "false",
        "scheduled_publish_time": str(_unix(scheduled_at)),
        "unpublished_content_type": "SCHEDULED",
        "attached_media[0]": json.dumps({"media_fbid": photo_id}),
    }

    if message.strip():
        data["message"] = message.strip()

    post = _post(f"{GRAPH_URL}/{page_id}/feed", data, "Facebook scheduling")

    return {"id": post.get("id"), "post_id": post.get("id")}


def delete_post(post_id: str, token: str) -> None:
    """Delete a post (used to cancel a scheduled post). A missing post counts as deleted."""

    try:
        response = requests.delete(f"{GRAPH_URL}/{post_id}", params={"access_token": token}, timeout=30)
    except requests.RequestException as exc:
        raise FacebookError(502, f"Facebook delete request failed: {str(exc)}")

    if response.status_code == 200:
        return

    result = _json(response, "Invalid response received from Facebook")
    error = result.get("error", {}) if isinstance(result, dict) else {}

    # code 100 / subcode 33 = the object no longer exists
    if error.get("code") == 100 or error.get("error_subcode") == 33:
        return

    raise FacebookError(400, {"message": "Facebook could not delete the post", "facebook_response": result})


def is_post_published(post_id: str, token: str) -> bool | None:
    """True/False when Facebook answers, None when the post cannot be found or checked."""

    try:
        response = requests.get(
            f"{GRAPH_URL}/{post_id}",
            params={"fields": "is_published", "access_token": token},
            timeout=30,
        )
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    try:
        return bool(response.json().get("is_published"))
    except ValueError:
        return None


def get_post_engagement(post_id: str, token: str) -> int | None:
    """Reactions + comments + shares of a post, or None when Facebook does not answer."""

    try:
        response = requests.get(
            f"{GRAPH_URL}/{post_id}",
            params={
                "fields": "reactions.summary(true).limit(0),comments.summary(true).limit(0),shares",
                "access_token": token,
            },
            timeout=30,
        )
    except requests.RequestException:
        return None

    if response.status_code != 200:
        return None

    try:
        data = response.json()
        reactions = data.get("reactions", {}).get("summary", {}).get("total_count", 0)
        comments = data.get("comments", {}).get("summary", {}).get("total_count", 0)
        shares = data.get("shares", {}).get("count", 0)

        return int(reactions) + int(comments) + int(shares)
    except (ValueError, TypeError, AttributeError):
        return None
