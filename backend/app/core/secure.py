import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

# The encryption key comes from FACEBOOK_TOKEN_KEY in .env. If it is not set, a key is
# created once and kept in backend/.token_key (this file is ignored by git).
KEY_FILE = Path(__file__).resolve().parents[2] / ".token_key"


def _load_key() -> bytes:
    from_env = os.getenv("FACEBOOK_TOKEN_KEY", "").strip()

    if from_env:
        return from_env.encode()

    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip().encode()

    key = Fernet.generate_key()
    KEY_FILE.write_text(key.decode(), encoding="utf-8")

    return key


def _fernet() -> Fernet:
    return Fernet(_load_key())


def encrypt_text(plain: str) -> str:
    return _fernet().encrypt(plain.encode()).decode()


def decrypt_text(token: str) -> str | None:
    try:
        return _fernet().decrypt(token.encode()).decode()
    except InvalidToken:
        return None
