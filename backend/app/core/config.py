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

    # low, medium or high (higher quality costs more and takes longer)
    OPENAI_IMAGE_QUALITY: str = os.getenv(
        "OPENAI_IMAGE_QUALITY",
        "high"
    )

    # Hugging Face - Mistral Text Generation (legacy, no longer used for chat)
    HF_TEXT_TOKEN: str = os.getenv(
        "HF_TEXT_TOKEN",
        ""
    )

    HF_TEXT_MODEL: str = os.getenv(
        "HF_TEXT_MODEL",
        "mistralai/Mistral-7B-Instruct-v0.2:featherless-ai"
    )

    # Hugging Face - Stable Diffusion Image Generation
    HF_IMAGE_TOKEN: str = os.getenv(
        "HF_IMAGE_TOKEN",
        ""
    )

    HF_IMAGE_MODEL: str = os.getenv(
        "HF_IMAGE_MODEL",
        "stabilityai/stable-diffusion-xl-base-1.0"
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


settings = Settings()


print("ENV FILE LOADED FROM:", ENV_PATH)
print("DB HOST:", settings.DB_HOST)
print("DB PORT:", settings.DB_PORT)
print("DB NAME:", settings.DB_NAME)
print("DB USER:", settings.DB_USER)
