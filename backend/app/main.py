from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.database import create_db_tables
from app.routers import auth, autopilot, chat, facebook, history, images, memory, schedule

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
)


@app.on_event("startup")
def on_startup():
    create_db_tables()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_URL,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
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


@app.get("/")
def home():
    return {
        "success": True,
        "message": "Marketing AI Backend is running with PostgreSQL chat history",
    }