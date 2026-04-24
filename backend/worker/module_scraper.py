import asyncio
import logging
from pathlib import Path

try:
    from playwright.async_api import (
        Error as PlaywrightError,
        TimeoutError as PlaywrightTimeoutError,
        async_playwright,
    )
except ModuleNotFoundError:  # pragma: no cover - fallback for test environments
    async_playwright = None

    class PlaywrightError(Exception):
        """Fallback Playwright base error when dependency is unavailable."""

    class PlaywrightTimeoutError(PlaywrightError):
        """Fallback Playwright timeout error when dependency is unavailable."""

from backend.config import SCRAPER_PAGE_TIMEOUT_SECONDS, get_job_dir
from backend.database import get_connection, log_message

logger = logging.getLogger(__name__)

ANTI_BOT_TOKENS = ("captcha", "verify", "challenge")
NETWORKIDLE_TIMEOUT_MS = 45_000
LAZY_LOAD_WAIT_MS = 2_000
MIN_HTML_LENGTH = 1_000


class ScraperError(RuntimeError):
    """Raised when scraping cannot produce a usable raw HTML snapshot."""


def _write_raw_html_sync(raw_dir: Path, html: str) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "index.html").write_text(html, encoding="utf-8")


def _log_job_message_sync(job_id: int, level: str, message: str) -> None:
    conn = get_connection()
    try:
        log_message(conn, job_id, level, message)
    finally:
        conn.close()


async def _log_job_message(job_id: int, level: str, message: str) -> None:
    await asyncio.to_thread(_log_job_message_sync, job_id, level, message)


def _is_anti_bot_redirect(target_url: str, current_url: str) -> bool:
    normalized_target = target_url.lower()
    normalized_current = current_url.lower()
    return normalized_current != normalized_target and any(
        token in normalized_current for token in ANTI_BOT_TOKENS
    )


async def _navigate(page: object, target_url: str) -> None:
    try:
        await page.goto(
            target_url,
            wait_until="domcontentloaded",
            timeout=SCRAPER_PAGE_TIMEOUT_SECONDS * 1000,
        )
    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        raise ScraperError("Target URL unreachable or timeout") from exc


async def _wait_for_network_idle(page: object, job_id: int) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=NETWORKIDLE_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        message = "networkidle timeout, using partial DOM"
        logger.warning("%s (job_id=%s)", message, job_id)
        await _log_job_message(job_id, "warn", message)


async def _collect_html(page: object) -> str:
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(LAZY_LOAD_WAIT_MS)
    return await page.content()


async def _rewrite_scraped_assets(
    *, job_id: int, target_url: str, raw_dir: Path, html: str
) -> str:
    return html


def _require_playwright() -> None:
    if async_playwright is None:
        raise RuntimeError("playwright package is not installed")


async def scrape(job_id: int, target_url: str) -> Path:
    raw_dir = get_job_dir(job_id) / "raw"
    _require_playwright()

    async with async_playwright() as playwright_api:
        browser = await playwright_api.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        try:
            context = await browser.new_context()
            page = await context.new_page()

            await _navigate(page, target_url)

            if _is_anti_bot_redirect(target_url, page.url):
                raise ScraperError("Target URL blocked by anti-bot")

            await _wait_for_network_idle(page, job_id)
            html = await _collect_html(page)
        finally:
            await browser.close()

    if len(html) < MIN_HTML_LENGTH:
        raise ScraperError("Scraped HTML too small, possible bot detection")

    html = await _rewrite_scraped_assets(
        job_id=job_id,
        target_url=target_url,
        raw_dir=raw_dir,
        html=html,
    )
    await asyncio.to_thread(_write_raw_html_sync, raw_dir, html)
    return raw_dir


async def module_scraper(job_id: int, target_url: str) -> None:
    await scrape(job_id, target_url)
