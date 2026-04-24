import asyncio
import logging
from pathlib import Path

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - fallback for test environments
    httpx = None  # type: ignore[assignment]

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

from backend.config import ASSET_DOWNLOAD_TIMEOUT_SECONDS, SCRAPER_PAGE_TIMEOUT_SECONDS, get_job_dir
from backend.database import get_connection, log_message
from backend.worker.asset_rewriter import AssetRewriteResult, rewrite_asset_urls
from backend.worker.css_url_rewriter import rewrite_css_urls
from backend.worker.dom_cleaner import clean_job_html

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


def _read_text_sync(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _write_text_sync(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


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
) -> AssetRewriteResult:
    (raw_dir / "assets").mkdir(parents=True, exist_ok=True)
    if httpx is None:
        logger.warning("httpx package is not installed, skipping asset rewrite (job_id=%s)", job_id)
        return AssetRewriteResult(html=html, css_file_origins={})
    timeout = httpx.Timeout(ASSET_DOWNLOAD_TIMEOUT_SECONDS)
    url_cache: dict[str, str] = {}
    used_filenames: dict[str, str] = {}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        rewrite_result = await rewrite_asset_urls(
            html=html,
            base_url=target_url,
            raw_dir=raw_dir,
            client=client,
            job_id=job_id,
            url_cache=url_cache,
            used_filenames=used_filenames,
        )
        assets_dir = raw_dir / "assets"
        for css_rel_path, css_origin_url in rewrite_result.css_file_origins.items():
            css_file_path = raw_dir / css_rel_path
            css_text = await asyncio.to_thread(_read_text_sync, css_file_path)
            rewritten_css = await rewrite_css_urls(
                css_text=css_text,
                css_file_base_url=css_origin_url,
                css_file_path=css_file_path,
                assets_dir=assets_dir,
                url_cache=url_cache,
                used_filenames=used_filenames,
                client=client,
                job_id=job_id,
            )
            await asyncio.to_thread(_write_text_sync, css_file_path, rewritten_css)
        return rewrite_result


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

    rewrite_result = await _rewrite_scraped_assets(
        job_id=job_id,
        target_url=target_url,
        raw_dir=raw_dir,
        html=html,
    )
    await asyncio.to_thread(_write_raw_html_sync, raw_dir, rewrite_result.html)
    return raw_dir


async def module_scraper(job_id: int, target_url: str) -> None:
    raw_dir = await scrape(job_id, target_url)
    result = await clean_job_html(job_id, raw_dir, base_url=target_url)
    stats = result.stats

    await _log_job_message(
        job_id, "info", f"dom_cleaner: removed tracker scripts: {stats.removed_tracker_scripts}"
    )
    await _log_job_message(
        job_id, "info", f"dom_cleaner: removed tracker iframes: {stats.removed_tracker_iframes}"
    )
    await _log_job_message(
        job_id, "info", f"dom_cleaner: removed noscript tags: {stats.removed_noscripts}"
    )
    await _log_job_message(job_id, "info", f"dom_cleaner: removed CSP meta tags: {stats.removed_csp_meta}")
    await _log_job_message(
        job_id, "info", f"dom_cleaner: removed HTML comments: {stats.removed_html_comments}"
    )
    await _log_job_message(
        job_id, "info", f"dom_cleaner: removed Google Fonts link tags: {stats.removed_google_font_links}"
    )
    await _log_job_message(
        job_id, "info", f"dom_cleaner: stripped Google Fonts @import rules: {stats.removed_font_imports}"
    )
    await _log_job_message(
        job_id, "info", f"dom_cleaner: unwrapped bdo/cite tags: {stats.removed_bdo_cite}"
    )
