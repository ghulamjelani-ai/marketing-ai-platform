import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.core.errors import ApiError
from app.core import guards, notify, poller
from app.core.idempotency import IdempotencyMiddleware
from app.core.mailer import check_email_settings
from sqlalchemy import text

from app.db.database import create_db_tables, engine
from app.routers import auth, autopilot, chat, facebook, history, images, memory, notifications, schedule, voice

guards.configure_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    insecure = settings.insecure_settings()

    if insecure and settings.APP_ENV == "production":
        raise RuntimeError("Set a real value for these in backend/.env before running in production: " + ", ".join(insecure))

    if insecure:
        print("WARNING: " + ", ".join(insecure) + " still has the default value. Set your own in backend/.env.")

    check_email_settings()
    create_db_tables()

    task = None

    if settings.BACKGROUND_POLLER and settings.APP_ENV != "test":
        task = asyncio.create_task(poller.run())

    try:
        yield
    finally:
        notify.flush(timeout=10)

        if task:
            task.cancel()

            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    lifespan=lifespan,
)


@app.exception_handler(ApiError)
def api_error_handler(request: Request, exc: ApiError):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


app.add_middleware(IdempotencyMiddleware)
app.add_middleware(guards.GuardMiddleware)

def cors_origins(env: str, frontend_url: str) -> tuple[list[str], str | None]:
    """The browser origins the API accepts: the real site, plus local addresses while developing.

    In production only the configured site is allowed, so a page running on someone's own
    computer cannot use a signed-in visitor's browser to call the API.
    """

    if env == "production":
        return [frontend_url], None

    return (
        [frontend_url, "http://localhost:5173", "http://127.0.0.1:5173"],
        # Vite moves to 5174, 5175... when 5173 is busy; any local port is fine in development.
        r"^http://(localhost|127\.0\.0\.1)(:\d+)?$",
    )


_origins, _origin_regex = cors_origins(settings.APP_ENV, settings.FRONTEND_URL)

# CORS is added last so it wraps everything, including idempotency answers.
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_origin_regex=_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/auth", tags=["Firebase Auth"])
app.include_router(chat.router, prefix="/chat", tags=["AI Chat"])
app.include_router(facebook.router, prefix="/facebook", tags=["Facebook"])
app.include_router(images.router, prefix="/images", tags=["AI Images"])
app.include_router(autopilot.router, prefix="/autopilot", tags=["Autopilot"])
app.include_router(history.router, prefix="/history", tags=["History"])
app.include_router(memory.router, prefix="/memory", tags=["Memory"])
app.include_router(schedule.router, prefix="/schedule", tags=["Scheduled Posts"])
app.include_router(voice.router, prefix="/voice", tags=["Voice"])
app.include_router(notifications.router, prefix="/notifications", tags=["Notifications"])


@app.get("/")
def home():
    return {
        "success": True,
        "message": "Marketing AI Backend is running with PostgreSQL chat history",
    }


@app.get("/health")
def health():
    """Is the process up? No database call, so a load balancer can poll it freely."""

    return {"status": "ok"}


@app.get("/ready")
def ready():
    """Can the app do its work? Checks the database."""

    try:
        with engine.connect() as connection:
            connection.execute(text("select 1"))
    except Exception:  # noqa: BLE001
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "error": {"code": "DB_UNAVAILABLE", "message": "The database is not reachable."}},
        )

    return {"status": "ready"}
