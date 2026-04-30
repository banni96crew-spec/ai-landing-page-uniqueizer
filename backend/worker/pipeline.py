import asyncio
import logging
from collections.abc import Awaitable, Callable

from backend.database import get_connection, log_message
from backend.worker.module_ai_rewriter import module_ai_rewriter
from backend.worker.module_dom_mutator import module_dom_mutator
from backend.worker.module_media import module_media_uniqueizer
from backend.worker.module_packer import module_packer
from backend.worker.module_scraper import module_scraper

PipelineStep = tuple[str, Callable[..., Awaitable[None]], tuple[object, ...]]
PROXY_URL_SETTING_KEY = "proxy_url"

logger = logging.getLogger(__name__)


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


def _get_setting_value_sync(key: str) -> str | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            (key,),
        ).fetchone()
        if row is None:
            return None
        value = str(row["value"]).strip()
        return value or None
    finally:
        conn.close()


async def get_setting_value(key: str) -> str | None:
    return await asyncio.to_thread(_get_setting_value_sync, key)


async def run_pipeline(job_id: int, target_url: str) -> None:
    proxy_url = await get_setting_value(PROXY_URL_SETTING_KEY)
    steps: tuple[PipelineStep, ...] = (
        ("MODULE_SCRAPER_DONE", module_scraper, (job_id, target_url, proxy_url)),
        ("MODULE_DOM_MUTATOR_DONE", module_dom_mutator, (job_id,)),
        ("MODULE_AI_REWRITER_DONE", module_ai_rewriter, (job_id,)),
        ("MODULE_MEDIA_UNIQUEIZER_DONE", module_media_uniqueizer, (job_id,)),
        ("MODULE_PACKER_DONE", module_packer, (job_id,)),
    )

    try:
        for marker, step, args in steps:
            step_name = getattr(step, "__name__", "pipeline_step")
            logger.info("pipeline: step_start %s marker=%s job_id=%s", step_name, marker, job_id)

            timeout_s = _step_timeout_seconds(marker)
            if timeout_s is None:
                await step(*args)
            else:
                try:
                    await asyncio.wait_for(step(*args), timeout=timeout_s)
                except asyncio.TimeoutError as exc:
                    raise TimeoutError(
                        f"Module timeout: {step_name} exceeded {timeout_s}s"
                    ) from exc

            await log_job_message(job_id, "info", marker)
            logger.info("pipeline: step_done %s marker=%s job_id=%s", step_name, marker, job_id)
    except Exception as exc:
        error_message = str(exc)
        logger.exception("Pipeline failed (job_id=%s)", job_id)
        await log_job_message(job_id, "error", error_message)
        await mark_job_failed(job_id, error_message)
        raise

    await mark_job_done(job_id)


def _step_timeout_seconds(marker: str) -> int | None:
    # Keep this intentionally conservative: per-step timeouts give fast, explicit failures
    # instead of "silent" hangs until the global JOB_TIMEOUT_SECONDS triggers.
    match marker:
        case "MODULE_SCRAPER_DONE":
            return 120
        case "MODULE_DOM_MUTATOR_DONE":
            return 120
        case "MODULE_AI_REWRITER_DONE":
            return 180
        case "MODULE_MEDIA_UNIQUEIZER_DONE":
            return 180
        case "MODULE_PACKER_DONE":
            return 180
        case _:
            return None
