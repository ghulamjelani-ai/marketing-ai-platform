import base64
import hashlib
import hmac
import os
import time
import uuid
from urllib.parse import urlencode

import requests
from dotenv import load_dotenv
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Form,
)
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core import facebook_api, notify
from app.core.errors import ApiError
from app.core.facebook_api import FacebookError, explain
from app.core.secure import decrypt_text, encrypt_text
from app.db.database import get_db
from app.models.models import FacebookConnection, FacebookPage, PublishedPost, User
from app.routers.auth import get_current_db_user

load_dotenv()

router = APIRouter()


# =========================================================
# CONFIG
# =========================================================

FACEBOOK_APP_ID = os.getenv("FACEBOOK_APP_ID")
FACEBOOK_APP_SECRET = os.getenv("FACEBOOK_APP_SECRET")

BACKEND_URL = os.getenv(
    "BACKEND_URL",
    "http://localhost:8000",
)

FRONTEND_URL = os.getenv(
    "FRONTEND_URL",
    "http://localhost:5173",
)

FACEBOOK_GRAPH_VERSION = facebook_api.GRAPH_VERSION

FACEBOOK_REDIRECT_URI = (
    f"{BACKEND_URL}/facebook/callback"
)

FACEBOOK_PERMISSIONS = [
    "pages_show_list",
    "pages_read_engagement",
    "pages_manage_posts",
]

STATE_MAX_AGE_SECONDS = 15 * 60


# =========================================================
# SIGNED "state" VALUE
# =========================================================
#
# Facebook sends the browser back to /facebook/callback without
# any login header, so the user identity travels in a signed
# state value that only this backend can create.
#
# =========================================================

def _state_key() -> bytes:
    if not FACEBOOK_APP_SECRET:
        raise HTTPException(
            status_code=500,
            detail="FACEBOOK_APP_SECRET is missing",
        )

    return FACEBOOK_APP_SECRET.encode()


def make_state(user_id: uuid.UUID) -> str:
    payload = f"{user_id}.{int(time.time())}"

    signature = hmac.new(
        _state_key(),
        payload.encode(),
        hashlib.sha256,
    ).hexdigest()

    raw = f"{payload}.{signature}"

    return base64.urlsafe_b64encode(raw.encode()).decode()


def read_state(state: str | None) -> uuid.UUID | None:
    if not state:
        return None

    try:
        raw = base64.urlsafe_b64decode(state.encode()).decode()
        user_id, issued_at, signature = raw.rsplit(".", 2)

        expected = hmac.new(
            _state_key(),
            f"{user_id}.{issued_at}".encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            return None

        if time.time() - int(issued_at) > STATE_MAX_AGE_SECONDS:
            return None

        return uuid.UUID(user_id)
    except (ValueError, TypeError):
        return None


# =========================================================
# HELPERS SHARED WITH THE SCHEDULER
# =========================================================

def get_user_connection(db: Session, user_id: uuid.UUID):
    """Returns (connection row, page access token) or (None, None)."""

    row = (
        db.query(FacebookConnection)
        .filter(FacebookConnection.user_id == user_id)
        .first()
    )

    if not row:
        return None, None

    token = decrypt_text(row.token_encrypted)

    return row, token


def token_for_post(db: Session, user_id: uuid.UUID, facebook_post_id: str | None) -> str | None:
    """The token of the Page a post belongs to. Post ids look like "PAGEID_POSTID", so a
    post made on another of the user's Pages still works after they switched Pages."""

    page_id = (facebook_post_id or "").split("_")[0]

    if page_id:
        page = (
            db.query(FacebookPage)
            .filter(FacebookPage.user_id == user_id, FacebookPage.page_id == page_id)
            .first()
        )

        if page:
            return decrypt_text(page.token_encrypted)

    return get_user_connection(db, user_id)[1]


def require_connection(db: Session, user: User):
    row, token = get_user_connection(db, user.id)

    if not row or not token:
        raise HTTPException(
            status_code=400,
            detail="Facebook Page is not connected",
        )

    return row, token


def record_published_post(
    db: Session,
    user_id: uuid.UUID,
    message: str,
    with_image: bool,
    facebook_post_id: str | None,
    source: str = "manual",
):
    db.add(
        PublishedPost(
            user_id=user_id,
            source=source,
            message=message,
            with_image=with_image,
            facebook_post_id=facebook_post_id,
        )
    )
    db.commit()


def raise_http(error: FacebookError):
    status_code, code, message = explain(error)
    print("Facebook call failed:", code, repr(error.detail)[:300])
    raise ApiError(status_code, code, message)


# =========================================================
# SCHEMAS
# =========================================================

class FacebookPostRequest(BaseModel):
    message: str


# =========================================================
# CONNECT FACEBOOK
# =========================================================

@router.get("/connect-url")
def get_facebook_connect_url(
    user: User = Depends(get_current_db_user),
):

    if not FACEBOOK_APP_ID:
        raise HTTPException(
            status_code=500,
            detail="FACEBOOK_APP_ID is missing",
        )

    params = {
        "client_id": FACEBOOK_APP_ID,
        "redirect_uri": FACEBOOK_REDIRECT_URI,
        "scope": ",".join(FACEBOOK_PERMISSIONS),
        "response_type": "code",
        "state": make_state(user.id),
    }

    connect_url = (
        f"https://www.facebook.com/"
        f"{FACEBOOK_GRAPH_VERSION}/dialog/oauth?"
        f"{urlencode(params)}"
    )

    return {
        "success": True,
        "connect_url": connect_url,
    }


# =========================================================
# FACEBOOK OAUTH CALLBACK
# =========================================================

@router.get("/callback")
def facebook_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):

    if error:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/home?facebook=error"
        )

    user_id = read_state(state)

    if not user_id:
        return RedirectResponse(
            url=f"{FRONTEND_URL}/home?facebook=error"
        )

    if not code:
        raise HTTPException(
            status_code=400,
            detail="Facebook authorization code missing",
        )

    if not FACEBOOK_APP_ID:
        raise HTTPException(
            status_code=500,
            detail="FACEBOOK_APP_ID is missing",
        )

    if not FACEBOOK_APP_SECRET:
        raise HTTPException(
            status_code=500,
            detail="FACEBOOK_APP_SECRET is missing",
        )

    # =====================================================
    # EXCHANGE AUTHORIZATION CODE
    # FOR USER ACCESS TOKEN
    # =====================================================

    token_url = (
        f"https://graph.facebook.com/"
        f"{FACEBOOK_GRAPH_VERSION}/oauth/access_token"
    )

    try:
        token_response = requests.get(
            token_url,
            params={
                "client_id": FACEBOOK_APP_ID,
                "client_secret": FACEBOOK_APP_SECRET,
                "redirect_uri": FACEBOOK_REDIRECT_URI,
                "code": code,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Facebook token request failed: {str(exc)}",
        )

    try:
        token_data = token_response.json()
    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="Invalid response received from Facebook",
        )

    if token_response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Facebook token exchange failed",
                "facebook_response": token_data,
            },
        )

    user_access_token = token_data.get(
        "access_token"
    )

    if not user_access_token:
        raise HTTPException(
            status_code=400,
            detail="Facebook did not return a user access token",
        )

    # =====================================================
    # GET FACEBOOK PAGES
    # =====================================================

    pages_url = (
        f"https://graph.facebook.com/"
        f"{FACEBOOK_GRAPH_VERSION}/me/accounts"
    )

    try:
        pages_response = requests.get(
            pages_url,
            params={
                "fields": (
                    "id,name,access_token,tasks"
                ),
                "access_token": user_access_token,
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Could not contact Facebook: {str(exc)}",
        )

    try:
        pages_data = pages_response.json()
    except ValueError:
        raise HTTPException(
            status_code=502,
            detail="Invalid Pages response from Facebook",
        )

    if pages_response.status_code != 200:
        raise HTTPException(
            status_code=400,
            detail={
                "message": "Could not retrieve Facebook Pages",
                "facebook_response": pages_data,
            },
        )

    pages = pages_data.get(
        "data",
        [],
    )

    if not pages:
        raise HTTPException(
            status_code=400,
            detail=(
                "No Facebook Pages were found for this account."
            ),
        )

    # Keep every Page the person manages, so they can choose where to post.
    usable = [p for p in pages if p.get("id") and p.get("access_token")]

    if not usable:
        raise HTTPException(
            status_code=400,
            detail="Facebook did not give access to any of your Pages. Please connect again and allow Page access.",
        )

    db.query(FacebookPage).filter(FacebookPage.user_id == user_id).delete()

    for item in usable:
        db.add(FacebookPage(
            user_id=user_id,
            page_id=item["id"],
            page_name=item.get("name"),
            token_encrypted=encrypt_text(item["access_token"]),
        ))

    row = (
        db.query(FacebookConnection)
        .filter(FacebookConnection.user_id == user_id)
        .first()
    )

    # Keep the Page chosen before if it is still available; otherwise start with the first.
    page = next((p for p in usable if row and p["id"] == row.page_id), usable[0])
    page_id = page["id"]
    page_name = page.get("name")

    if row is None:
        row = FacebookConnection(
            user_id=user_id,
            page_id=page_id,
            page_name=page_name,
            token_encrypted=encrypt_text(page["access_token"]),
        )
        db.add(row)
    else:
        row.page_id = page_id
        row.page_name = page_name
        row.token_encrypted = encrypt_text(page["access_token"])

    db.commit()

    print("FACEBOOK PAGES CONNECTED:", len(usable))

    return RedirectResponse(
        url=f"{FRONTEND_URL}/home?facebook=connected&pages={len(usable)}"
    )


# =========================================================
# FACEBOOK CONNECTION STATUS
# =========================================================

@router.get("/status")
def facebook_status(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):

    row, token = get_user_connection(db, user.id)

    connected = bool(row and token)

    return {
        "success": True,
        "connected": connected,
        "page_id": row.page_id if connected else None,
        "page_name": row.page_name if connected else None,
        "page_count": (
            db.query(FacebookPage).filter(FacebookPage.user_id == user.id).count() if connected else 0
        ),
    }


class SelectPageRequest(BaseModel):
    page_id: str


@router.get("/pages")
def list_pages(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    """All Pages saved at connect time; `selected` marks the one posts go to."""

    row, _ = get_user_connection(db, user.id)
    pages = (
        db.query(FacebookPage)
        .filter(FacebookPage.user_id == user.id)
        .order_by(FacebookPage.page_name)
        .all()
    )

    return {
        "success": True,
        "pages": [
            {"page_id": p.page_id, "page_name": p.page_name, "selected": bool(row and p.page_id == row.page_id)}
            for p in pages
        ],
    }


@router.post("/select-page")
def select_page(
    payload: SelectPageRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):
    """Makes one of the user's own saved Pages the one new posts go to."""

    page = (
        db.query(FacebookPage)
        .filter(FacebookPage.user_id == user.id, FacebookPage.page_id == payload.page_id)
        .first()
    )

    if page is None:
        raise ApiError(404, "PAGE_NOT_FOUND", "That Page is not connected to your account. Connect Facebook again.")

    row = db.query(FacebookConnection).filter(FacebookConnection.user_id == user.id).first()

    if row is None:
        raise ApiError(400, "FB_NOT_CONNECTED", "Connect your Facebook Page first.")

    row.page_id = page.page_id
    row.page_name = page.page_name
    row.token_encrypted = page.token_encrypted
    db.commit()

    return {"success": True, "page_id": page.page_id, "page_name": page.page_name}


# =========================================================
# PUBLISH TEXT POST
# =========================================================

@router.post("/publish")
def publish_to_facebook(
    payload: FacebookPostRequest,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):

    row, token = require_connection(db, user)

    message = payload.message.strip()

    if not message:
        raise HTTPException(
            status_code=400,
            detail="Post message cannot be empty",
        )

    try:
        result = facebook_api.publish_text(
            row.page_id,
            token,
            message,
        )
    except FacebookError as error:
        raise_http(error)

    record_published_post(
        db,
        user.id,
        message,
        False,
        result.get("id"),
    )

    notify.submit(
        user.email,
        "published",
        user_id=user.id,
        page_name=getattr(row, "page_name", None),
        text=message,
        post_id=result.get("id"),
    )

    return {
        "success": True,
        "message": "Post published successfully",
        "post_id": result.get("id"),
    }


# =========================================================
# PUBLISH PHOTO + CAPTION
# =========================================================

@router.post("/publish-photo")
async def publish_photo_to_facebook(
    message: str = Form(""),
    image: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):

    row, token = require_connection(db, user)

    # =====================================================
    # VALIDATE IMAGE
    # =====================================================

    if not image.content_type:
        raise HTTPException(
            status_code=400,
            detail="Image type could not be detected",
        )

    if not image.content_type.startswith(
        "image/"
    ):
        raise HTTPException(
            status_code=400,
            detail="Please upload a valid image file",
        )

    # Optional safety limit
    max_image_size = 15 * 1024 * 1024

    image_bytes = await image.read()

    if not image_bytes:
        raise HTTPException(
            status_code=400,
            detail="Uploaded image is empty",
        )

    if len(image_bytes) > max_image_size:
        raise HTTPException(
            status_code=400,
            detail="Image is too large. Maximum size is 15 MB.",
        )

    try:
        result = facebook_api.publish_photo(
            row.page_id,
            token,
            image_bytes,
            image.filename or "facebook-image.jpg",
            image.content_type,
            message,
        )
    except FacebookError as error:
        raise_http(error)

    record_published_post(
        db,
        user.id,
        message.strip(),
        True,
        result.get("post_id") or result.get("id"),
    )

    notify.submit(
        user.email,
        "published",
        user_id=user.id,
        page_name=getattr(row, "page_name", None),
        text=message.strip(),
        post_id=result.get("post_id") or result.get("id"),
        with_image=True,
    )

    return {
        "success": True,
        "message": "Photo published successfully",
        "photo_id": result.get("id"),
        "post_id": result.get("post_id"),
    }


# =========================================================
# DISCONNECT FACEBOOK
# =========================================================

@router.post("/disconnect")
def disconnect_facebook(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_db_user),
):

    db.query(FacebookConnection).filter(
        FacebookConnection.user_id == user.id
    ).delete()
    db.query(FacebookPage).filter(FacebookPage.user_id == user.id).delete()
    db.commit()

    return {
        "success": True,
        "message": "Facebook Page disconnected",
    }
