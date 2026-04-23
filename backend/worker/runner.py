import asyncio
import logging
from typing import Any

from backend.config import JOB_TIMEOUT_SECONDS, WORKER_POLL_INTERVAL
from backend.database import get_connection
from backend.state import JOB_QUEUES
from backend.worker.pipeline import log_job_message, mark_job_failed, run_pipeline

logger = logging.getLogger(__name__)

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
        row = conn.execute(
            """
            SELECT *
            FROM jobs
            WHERE status = ?
            ORDER BY created_at ASC
            LIMIT 1
            """,
            ("pending",),
        ).fetchone()

        if row is None:
            return None

        job_id = row["id"]
        cursor = conn.execute(
            """
            UPDATE jobs
            SET status = ?
            WHERE id = ? AND status = ?
            """,
            ("running", job_id, "pending"),
        )

        if cursor.rowcount != 1:
            return None

        conn.commit()
        return dict(row)
    finally:
        conn.close()


async def claim_next_pending_job() -> dict[str, Any] | None:
    return await asyncio.to_thread(_claim_next_pending_job_sync)


async def worker_loop() -> None:
    while True:
        try:
            job = await claim_next_pending_job()

            if job is None:
                await asyncio.sleep(WORKER_POLL_INTERVAL)
                continue

            job_id = int(job["id"])
            target_url = str(job["target_url"])
            JOB_QUEUES[job_id] = asyncio.Queue(maxsize=1000)

            try:
                await asyncio.wait_for(
                    run_pipeline(job_id, target_url),
                    timeout=JOB_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError:
                error_message = f"Pipeline timeout after {JOB_TIMEOUT_SECONDS}s"
                await log_job_message(job_id, "error", error_message)
                await mark_job_failed(job_id, error_message)
            except Exception as exc:
                # Fallback guard in case pipeline exception handling
                # fails before writing the terminal failed state.
                await mark_job_failed(job_id, str(exc))
            finally:
                JOB_QUEUES.pop(job_id, None)
        except asyncio.CancelledError:
            raise
        except Exception:
            # Top-level guard: worker must never crash the process.
            logger.exception("Worker loop unexpected error")
            await asyncio.sleep(WORKER_POLL_INTERVAL)


async def poll_loop() -> None:
    await worker_loop()
