import asyncio
import logging
import os
from typing import Any

from backend.config import JOB_TIMEOUT_SECONDS, WORKER_POLL_INTERVAL
from backend.database import get_connection
from backend.state import JOB_QUEUES
from backend.worker.pipeline import log_job_message, mark_job_failed, run_pipeline

logger = logging.getLogger(__name__)

_MODULE_LOGGER_CONFIGURED = False


def _ensure_worker_console_logging() -> None:
    """Standalone worker has no uvicorn logging; without this, logger.info is invisible."""
    global _MODULE_LOGGER_CONFIGURED
    if _MODULE_LOGGER_CONFIGURED:
        return
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        )
    for noisy in ("httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _MODULE_LOGGER_CONFIGURED = True


MODULE_DONE_MARKERS = {
    "MODULE_SCRAPER_DONE",
    "MODULE_DOM_MUTATOR_DONE",
    "MODULE_AI_REWRITER_DONE",
    "MODULE_MEDIA_UNIQUEIZER_DONE",
    "MODULE_PACKER_DONE",
}

def _claim_next_pending_job_sync() -> dict[str, Any] | None:
    conn = get_connection()
    try:
        all_rows = conn.execute("SELECT * FROM jobs").fetchall()
        print(f"🔍 В базе {len(all_rows)} задач. Проверяю каждую:")

        target_row = None
        for row in all_rows:
            raw_status = row["status"]
            clean_status = str(raw_status).strip().lower()

            # ВЫВОДИМ ПОДРОБНОСТИ О КАЖДОЙ ЗАДАЧЕ
            print(f"   - ID {row['id']}: статус='{raw_status}' | длина={len(str(raw_status))} | после чистки='{clean_status}'")

            # Проверяем "мягким" поиском (если в статусе есть хоть намек на pend)
            if "pend" in clean_status:
                target_row = row
                break

        if target_row is None:
            print("   ❌ Ни одна задача не подошла под фильтр 'pending'")
            return None

        job_id = target_row["id"]
        print(f"🎯 ПОДХОДИТ! Забираю ID {job_id}")
        conn.execute("UPDATE jobs SET status = 'running' WHERE id = ?", (job_id,))
        return dict(target_row)
    except Exception as e:
        print(f"❌ ОШИБКА БД: {e}")
        import traceback
        traceback.print_exc()
        return None
    finally:
        conn.close()

async def claim_next_pending_job() -> dict[str, Any] | None:
    return await asyncio.to_thread(_claim_next_pending_job_sync)

async def worker_loop() -> None:
    _ensure_worker_console_logging()
    while True:
        try:
            job = await claim_next_pending_job()

            if job is None:
                # Если задач нет, просто тихо ждем
                await asyncio.sleep(WORKER_POLL_INTERVAL)
                continue

            job_id = int(job["id"])
            target_url = str(job["target_url"])
            print(f"🚀 ЗАПУСК ПАЙПЛАЙНА для задачи {job_id} ({target_url})", flush=True)

            JOB_QUEUES[job_id] = asyncio.Queue(maxsize=1000)

            try:
                print(f"[job {job_id}] DB log: pipeline_start …", flush=True)
                await log_job_message(job_id, "info", "worker: pipeline_start")
                print(
                    f"[job {job_id}] run_pipeline (timeout {JOB_TIMEOUT_SECONDS}s) …",
                    flush=True,
                )
                await asyncio.wait_for(
                    run_pipeline(job_id, target_url),
                    timeout=JOB_TIMEOUT_SECONDS,
                )
                print(f"✅ Задача {job_id} успешно завершена!", flush=True)
            except asyncio.TimeoutError:
                error_message = f"Pipeline timeout after {JOB_TIMEOUT_SECONDS}s"
                await log_job_message(job_id, "error", error_message)
                await mark_job_failed(job_id, error_message)
            except Exception as pipeline_error:
                print(f"❌ Ошибка в пайплайне: {pipeline_error}")
                await mark_job_failed(job_id, str(pipeline_error))
            finally:
                JOB_QUEUES.pop(job_id, None)

        except Exception as e:
            print(f"\n❌ КРИТИЧЕСКАЯ ОШИБКА ВОРКЕРА: {e}")
            await asyncio.sleep(WORKER_POLL_INTERVAL)

if __name__ == "__main__":
    _ensure_worker_console_logging()
    print("\n🚀 --- БОЕВОЙ ВОРКЕР ЗАПУЩЕН ---")
    print("Использую метод прямого поиска задач...\n")

    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        print("\n🛑 Воркер остановлен.")