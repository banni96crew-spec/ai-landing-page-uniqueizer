import asyncio
import logging
import shutil
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Используем твои готовые конфиги и БД
from backend.config import (
    ARTIFACTS_DIR,
    ARTIFACT_TTL_DAYS,
    CORS_ORIGINS,
    FAILED_JOB_TTL_DAYS,
    JOBS_WORKDIR,
    get_artifact_path,
    get_job_dir,
)
from backend.database import get_connection, init_db
from backend.routers.artifacts import router as artifacts_router
from backend.routers.jobs import router as jobs_router
from backend.routers.settings import router as settings_router
from backend.worker.runner import poll_loop

logger = logging.getLogger(__name__)


def _cleanup_expired_jobs_sync() -> None:
    conn = get_connection()
    try:
        done_rows = conn.execute(
            "SELECT id FROM jobs WHERE status='done' "
            "AND updated_at < datetime('now', ?)",
            (f"-{ARTIFACT_TTL_DAYS} days",),
        ).fetchall()
        failed_rows = conn.execute(
            "SELECT id FROM jobs WHERE status='failed' "
            "AND updated_at < datetime('now', ?)",
            (f"-{FAILED_JOB_TTL_DAYS} days",),
        ).fetchall()

        for row in done_rows:
            job_id = int(row["id"])
            artifact_path = get_artifact_path(job_id)
            job_dir = get_job_dir(job_id)

            if artifact_path.exists():
                artifact_path.unlink()
            if job_dir.exists():
                shutil.rmtree(job_dir)

            conn.execute("DELETE FROM logs WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM artifacts WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

        for row in failed_rows:
            job_id = int(row["id"])
            artifact_path = get_artifact_path(job_id)
            job_dir = get_job_dir(job_id)

            if artifact_path.exists():
                artifact_path.unlink()
            if job_dir.exists():
                shutil.rmtree(job_dir)

            conn.execute("DELETE FROM logs WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM artifacts WHERE job_id = ?", (job_id,))
            conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))

        conn.commit()
    finally:
        conn.close()


async def _ttl_cleanup_loop() -> None:
    while True:
        await asyncio.sleep(86400)
        try:
            await asyncio.to_thread(_cleanup_expired_jobs_sync)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("TTL cleanup loop unexpected error")


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
            "UPDATE jobs SET status='failed', "
            "error_message='Interrupted by server restart' "
            "WHERE status='running'"
        )
        conn.commit()
    finally:
        conn.close()

    worker_task = asyncio.create_task(poll_loop())
    cleanup_task = asyncio.create_task(_ttl_cleanup_loop())

    yield

    worker_task.cancel()
    cleanup_task.cancel()
    for task in (worker_task, cleanup_task):
        try:
            await task
        except asyncio.CancelledError:
            pass

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