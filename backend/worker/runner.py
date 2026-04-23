import asyncio
import logging
from typing import Any

from backend.config import JOB_TIMEOUT_SECONDS, WORKER_POLL_INTERVAL
from backend.database import get_connection, log_message
from backend.state import JOB_QUEUES

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
        conn.close()
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
        conn.close()
        return None

    conn.commit()
    conn.close()
    return dict(row)


def _mark_done_sync(job_id: int) -> None:
    conn = get_connection()
    conn.execute(
        """
        UPDATE jobs
        SET status = ?, error_message = NULL
        WHERE id = ? AND status = ?
        """,
        ("done", job_id, "running"),
    )
    conn.commit()
    conn.close()


def _mark_failed_sync(job_id: int, error_message: str) -> None:
    conn = get_connection()
    conn.execute(
        """
        UPDATE jobs
        SET status = ?, error_message = ?
        WHERE id = ? AND status = ?
        """,
        ("failed", error_message, job_id, "running"),
    )
    conn.commit()
    conn.close()


def _log_sync(job_id: int, level: str, message: str) -> None:
    conn = get_connection()
    try:
        log_message(conn, job_id, level, message)
    finally:
        conn.close()


async def claim_next_pending_job() -> dict[str, Any] | None:
    return await asyncio.to_thread(_claim_next_pending_job_sync)


async def _mark_done(job_id: int) -> None:
    await asyncio.to_thread(_mark_done_sync, job_id)


async def _mark_failed(job_id: int, error_message: str) -> None:
    await asyncio.to_thread(_mark_failed_sync, job_id, error_message)


async def _log(job_id: int, level: str, message: str) -> None:
    await asyncio.to_thread(_log_sync, job_id, level, message)


async def run_pipeline(job_id: int, target_url: str) -> None:
    await _log(job_id, "info", f"Starting... target_url={target_url}")
    await asyncio.sleep(5)
    await _log(job_id, "info", "Finished")


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
                await _mark_failed(
                    job_id,
                    f"Pipeline timeout after {JOB_TIMEOUT_SECONDS}s",
                )
            except Exception as exc:
                await _mark_failed(job_id, str(exc))
            else:
                await _mark_done(job_id)
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
