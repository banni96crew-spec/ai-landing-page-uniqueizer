import asyncio
from collections.abc import Awaitable, Callable

from backend.database import get_connection, log_message

PipelineStep = tuple[str, Callable[..., Awaitable[None]], tuple[object, ...]]


def _mark_done_sync(job_id: int) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, error_message = NULL
            WHERE id = ? AND status = ?
            """,
            ("done", job_id, "running"),
        )
        conn.commit()
    finally:
        conn.close()


def _mark_failed_sync(job_id: int, error_message: str) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, error_message = ?
            WHERE id = ? AND status = ?
            """,
            ("failed", error_message, job_id, "running"),
        )
        conn.commit()
    finally:
        conn.close()


def _log_sync(job_id: int, level: str, message: str) -> None:
    conn = get_connection()
    try:
        log_message(conn, job_id, level, message)
    finally:
        conn.close()


async def log_job_message(job_id: int, level: str, message: str) -> None:
    await asyncio.to_thread(_log_sync, job_id, level, message)


async def mark_job_done(job_id: int) -> None:
    await asyncio.to_thread(_mark_done_sync, job_id)


async def mark_job_failed(job_id: int, error_message: str) -> None:
    await asyncio.to_thread(_mark_failed_sync, job_id, error_message)


async def module_scraper(job_id: int, target_url: str) -> None:
    _ = (job_id, target_url)
    await asyncio.sleep(1)


async def module_dom_mutator(job_id: int) -> None:
    _ = job_id
    await asyncio.sleep(1)


async def module_ai_rewriter(job_id: int) -> None:
    _ = job_id
    await asyncio.sleep(1)


async def module_media_uniqueizer(job_id: int) -> None:
    _ = job_id
    await asyncio.sleep(1)


async def module_packer(job_id: int) -> None:
    _ = job_id
    await asyncio.sleep(1)


async def run_pipeline(job_id: int, target_url: str) -> None:
    steps: tuple[PipelineStep, ...] = (
        ("MODULE_SCRAPER_DONE", module_scraper, (job_id, target_url)),
        ("MODULE_DOM_MUTATOR_DONE", module_dom_mutator, (job_id,)),
        ("MODULE_AI_REWRITER_DONE", module_ai_rewriter, (job_id,)),
        ("MODULE_MEDIA_UNIQUEIZER_DONE", module_media_uniqueizer, (job_id,)),
        ("MODULE_PACKER_DONE", module_packer, (job_id,)),
    )

    try:
        for marker, step, args in steps:
            await step(*args)
            await log_job_message(job_id, "info", marker)
    except Exception as exc:
        error_message = str(exc)
        await log_job_message(job_id, "error", error_message)
        await mark_job_failed(job_id, error_message)
        raise

    await mark_job_done(job_id)
