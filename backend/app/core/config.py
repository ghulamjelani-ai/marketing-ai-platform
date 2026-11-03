import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"

load_dotenv(dotenv_path=ENV_PATH, override=True)


class Settings:
    APP_NAME: str = os.getenv(
        "APP_NAME",
        "Marketing AI Backend"
    )

    FRONTEND_URL: str = os.getenv(
        "FRONTEND_URL",
        "http://localhost:5173"
    )

    FIREBASE_CREDENTIALS_PATH: str = os.getenv(
        "FIREBASE_CREDENTIALS_PATH",
        ""
    )

    # OpenAI - Chat / marketing plan generation
    OPENAI_API_KEY: str = os.getenv(
        "OPENAI_API_KEY",
        ""
    )

    # Set the model name in .env (for example OPENAI_MODEL=<model id>)
    OPENAI_MODEL: str = os.getenv(
        "OPENAI_MODEL",
        ""
    )

    # OpenAI - Image generation (gpt-image-1 was tested with this project's key)
    OPENAI_IMAGE_MODEL: str = os.getenv(
        "OPENAI_IMAGE_MODEL",
        "gpt-image-1"
    )

    # Fallback lists, comma separated, best choice first. If one model fails the next is tried.
    # Leave empty to use only OPENAI_MODEL / OPENAI_IMAGE_MODEL.
    OPENAI_MODELS: str = os.getenv(
        "OPENAI_MODELS",
        ""
    )

    OPENAI_IMAGE_MODELS: str = os.getenv(
        "OPENAI_IMAGE_MODELS",
        ""
    )

    @staticmethod
    def _model_list(primary: str, extra: str) -> list[str]:
        names = [primary] + extra.split(",")
        result: list[str] = []

        for name in names:
            name = name.strip()
            if name and name not in result:
                result.append(name)

        return result

    # Speech to text for the voice button, best choice first (comma separated).
    OPENAI_TRANSCRIBE_MODELS: str = os.getenv(
        "OPENAI_TRANSCRIBE_MODELS",
        "gpt-4o-mini-transcribe,whisper-1"
    )

    @property
    def transcribe_model_list(self) -> list[str]:
        return self._model_list("", self.OPENAI_TRANSCRIBE_MODELS)

    @property
    def chat_model_list(self) -> list[str]:
        return self._model_list(self.OPENAI_MODEL, self.OPENAI_MODELS)

    @property
    def image_model_list(self) -> list[str]:
        return self._model_list(self.OPENAI_IMAGE_MODEL, self.OPENAI_IMAGE_MODELS)

    # low, medium or high (higher quality costs more and takes longer)
    OPENAI_IMAGE_QUALITY: str = os.getenv(
        "OPENAI_IMAGE_QUALITY",
        "high"
    )

    # Database
    DB_HOST: str = os.getenv(
        "DB_HOST",
        "127.0.0.1"
    )

    DB_PORT: int = int(
        os.getenv("DB_PORT", "5432")
    )

    DB_NAME: str = os.getenv(
        "DB_NAME",
        "marketing_ai_db"
    )

    DB_USER: str = os.getenv(
        "DB_USER",
        "marketing_ai_user"
    )

    DB_PASSWORD: str = os.getenv(
        "DB_PASSWORD",
        "12345"
    )

    # development | test | production. Production refuses to start without email settings.
    APP_ENV: str = os.getenv("APP_ENV", "development").strip().lower()

    # Email (SMTP) for the 6-digit sign-in codes. See .env.example for Gmail,
    # the local sandbox inbox (localhost:1025) and transactional providers.
    SMTP_HOST: str = os.getenv("SMTP_HOST", "").strip()
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587") or "587")
    SMTP_USERNAME: str = os.getenv("SMTP_USERNAME", "").strip()
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM_EMAIL: str = os.getenv("SMTP_FROM_EMAIL", "").strip()
    SMTP_FROM_NAME: str = os.getenv("SMTP_FROM_NAME", "Marketing AI").strip()
    # STARTTLS (usually port 587) or SSL from the first byte (port 465). The sandbox uses neither.
    SMTP_USE_TLS: bool = os.getenv("SMTP_USE_TLS", "true").strip().lower() in ("1", "true", "yes")
    SMTP_USE_SSL: bool = os.getenv("SMTP_USE_SSL", "false").strip().lower() in ("1", "true", "yes")
    SMTP_TIMEOUT: float = float(os.getenv("SMTP_TIMEOUT", "10") or "10")

    # Emails to the account address when a post is published, scheduled, goes live or is edited.
    POST_NOTIFICATIONS: bool = os.getenv("POST_NOTIFICATIONS", "true").strip().lower() in ("1", "true", "yes")
    # Send post emails inside the request instead of on the background worker (used by the tests).
    NOTIFY_INLINE: bool = os.getenv("NOTIFY_INLINE", "false").strip().lower() in ("1", "true", "yes")

    # A background check that marks due scheduled posts as live (and emails the owner)
    # even when nobody has the site open. It runs inside the single backend process.
    BACKGROUND_POLLER: bool = os.getenv("BACKGROUND_POLLER", "true").strip().lower() in ("1", "true", "yes")
    POLL_SECONDS: int = max(60, int(os.getenv("POLL_SECONDS", "300") or "300"))

    def insecure_settings(self) -> list[str]:
        """Names of settings that must be changed before a production start."""

        problems = []

        if self.DB_PASSWORD in ("", "12345"):
            problems.append("DB_PASSWORD")

        return problems

    def missing_email_settings(self) -> list[str]:
        """Names (never values) of the email settings that still need a value."""

        needed = ["SMTP_HOST", "SMTP_FROM_EMAIL"]

        # A local sandbox needs no login; a real mail server does.
        if self.APP_ENV == "production":
            needed += ["SMTP_USERNAME", "SMTP_PASSWORD"]

        return [name for name in needed if not getattr(self, name)]


settings = Settings()
