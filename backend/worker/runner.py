import sys
import asyncio
import logging
# --- ИНЪЕКЦИЯ ДЛЯ WINDOWS И PLAYWRIGHT ---
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from typing import Any

from backend.config import JOB_TIMEOUT_SECONDS, WORKER_POLL_INTERVAL
from backend.database import get_connection
from backend.state import JOB_QUEUES, set_ws_broadcast_loop
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
        # EC-15: atomic claim (pending -> running) with rowcount check.
        # Use an explicit transaction to avoid races under concurrent workers.
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT id, target_url FROM jobs WHERE status = 'pending' "
            "ORDER BY created_at ASC LIMIT 1"
        ).fetchone()
        if row is None:
            conn.execute("COMMIT")
            return None

        job_id = int(row["id"])
        cursor = conn.execute(
            "UPDATE jobs SET status = 'running' WHERE id = ? AND status = 'pending'",
            (job_id,),
        )
        if cursor.rowcount != 1:
            conn.execute("COMMIT")
            return None

        conn.execute("COMMIT")
        return {"id": job_id, "target_url": str(row["target_url"])}
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        logger.exception("DB error while claiming pending job")
        return None
    finally:
        conn.close()

async def claim_next_pending_job() -> dict[str, Any] | None:
    return await asyncio.to_thread(_claim_next_pending_job_sync)


async def worker_loop() -> None:
    _ensure_worker_console_logging()
    set_ws_broadcast_loop(asyncio.get_running_loop())
    while True:
        try:
            job = await claim_next_pending_job()

            if job is None:
                # Если задач нет, просто тихо ждем
                await asyncio.sleep(WORKER_POLL_INTERVAL)
                continue

            job_id = int(job["id"])
            target_url = str(job["target_url"])
            logger.info("worker: claimed job_id=%s target_url=%s", job_id, target_url)

            JOB_QUEUES[job_id] = asyncio.Queue(maxsize=1000)

            try:
                await log_job_message(job_id, "info", "MARKER:pipeline_started")
                await asyncio.wait_for(
                    run_pipeline(job_id, target_url),
                    timeout=JOB_TIMEOUT_SECONDS,
                )
                logger.info("worker: pipeline finished job_id=%s", job_id)

            except asyncio.TimeoutError:
                error_message = f"Pipeline timeout after {JOB_TIMEOUT_SECONDS}s"
                await log_job_message(job_id, "error", error_message)
                await mark_job_failed(job_id, error_message)
            except Exception as pipeline_error:
                logger.exception("worker: pipeline failed job_id=%s", job_id)
                await mark_job_failed(job_id, str(pipeline_error))
            finally:
                JOB_QUEUES.pop(job_id, None)

        except Exception as e:
            logger.exception("worker_loop unexpected error")
            await asyncio.sleep(WORKER_POLL_INTERVAL)

if __name__ == "__main__":
    _ensure_worker_console_logging()
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        pass