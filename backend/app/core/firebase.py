import os

import firebase_admin
from firebase_admin import auth as firebase_auth
from firebase_admin import credentials
from fastapi import HTTPException, status

from app.core.config import settings


def get_firebase_app():
    """
    Initialize Firebase Admin SDK only when needed.
    This keeps backend running even if service account is not added yet.
    """

    if firebase_admin._apps:
        return firebase_admin.get_app()

    credentials_path = settings.FIREBASE_CREDENTIALS_PATH

    if credentials_path and os.path.exists(credentials_path):
        cred = credentials.Certificate(credentials_path)
        return firebase_admin.initialize_app(cred)

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=(
            "Firebase Admin service account is not configured. "
            "Add FIREBASE_CREDENTIALS_PATH in .env later."
        ),
    )


def verify_firebase_token(id_token: str):
    """
    Verify Firebase ID token from frontend.
    """

    try:
        get_firebase_app()
        decoded_token = firebase_auth.verify_id_token(id_token)

        return {
            "uid": decoded_token.get("uid"),
            "email": decoded_token.get("email"),
            "name": decoded_token.get("name"),
            "picture": decoded_token.get("picture"),
            "email_verified": bool(decoded_token.get("email_verified")),
            "auth_time": int(decoded_token.get("auth_time") or 0),
            "provider": (decoded_token.get("firebase") or {}).get("sign_in_provider", ""),
        }

    except HTTPException:
        raise

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired Firebase token: {str(error)}",
        )

def find_account(email: str) -> str | None:
    """The Firebase uid of an active account with this email (password or Google), else None.

    A Google-only account gets a password added when it is reset: the emailed code
    proves the person owns the address.
    """

    get_firebase_app()

    try:
        record = firebase_auth.get_user_by_email(email)
    except firebase_auth.UserNotFoundError:
        return None

    return None if record.disabled else record.uid


def set_password(uid: str, new_password: str) -> None:
    """Sets a new password. Firebase itself then ends the account's other sessions.

    revoke_refresh_tokens() is deliberately not called: it stamps "sessions before now
    are invalid" with this computer's clock, and a clock running a few minutes fast
    then rejects every new login for those minutes.
    """

    get_firebase_app()
    firebase_auth.update_user(uid, password=new_password)
