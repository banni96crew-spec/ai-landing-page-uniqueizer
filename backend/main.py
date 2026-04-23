from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Используем твои готовые конфиги и БД
from backend.config import ARTIFACTS_DIR, CORS_ORIGINS, JOBS_WORKDIR
from backend.database import get_connection, init_db
from backend.routers.artifacts import router as artifacts_router
from backend.routers.jobs import router as jobs_router
from backend.routers.settings import router as settings_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP (Запуск) ---
    JOBS_WORKDIR.mkdir(parents=True, exist_ok=True)
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    # Инициализация таблиц
    init_db()

    # Логика EC-16: чистим зависшие задачи
    conn = get_connection()
    try:
        conn.execute(
            "UPDATE jobs SET status='failed', error_message='Worker interrupted' "
            "WHERE status='running'"
        )
        conn.commit()
        print("✅ Startup: Interrupted jobs marked as failed.")
    finally:
        conn.close()

    yield
    # --- SHUTDOWN (Выключение) ---
    print("Cleanup on shutdown...")

app = FastAPI(title="AI Landing Page Uniqueizer", lifespan=lifespan)

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

app.include_router(jobs_router)
app.include_router(settings_router)
app.include_router(artifacts_router)

@app.get("/")
async def root():
    return {"status": "online", "message": "API is ready"}