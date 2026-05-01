import asyncio
import logging
import random
from pathlib import Path
from typing import TypedDict
from urllib.parse import unquote, urlsplit

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

try:
    from playwright_stealth import stealth_async
except ModuleNotFoundError:  # pragma: no cover - fallback for test environments
    async def stealth_async(page: object) -> None:
        del page
        return None

from backend.config import ASSET_DOWNLOAD_TIMEOUT_SECONDS, SCRAPER_PAGE_TIMEOUT_SECONDS, get_job_dir
from backend.database import get_connection, log_message
from backend.worker.asset_rewriter import AssetRewriteResult, rewrite_asset_urls
from backend.worker.css_url_rewriter import rewrite_css_urls
from backend.worker.dom_cleaner import finalize_clean_sync, prepare_clean_sync
from backend.worker.google_fonts import download_google_fonts

logger = logging.getLogger(__name__)

ANTI_BOT_TOKENS = ("captcha", "verify", "challenge")
CHALLENGE_PAGE_TOKENS = (
    "attention required",
    "cf-challenge",
    "checking your browser",
    "just a moment",
    "verify you are human",
)
NETWORKIDLE_TIMEOUT_MS = 45_000
LAZY_LOAD_WAIT_MS = 2_000
CHALLENGE_SETTLE_POLL_MS = 1_500
CHALLENGE_SETTLE_ATTEMPTS = 3
HUMAN_DELAY_RANGE_MS = (2_000, 5_000)
ACTION_JITTER_RANGE_MS = (250, 900)
RETRY_BACKOFF_RANGE_MS = (1_000, 2_500)
MAX_BLOCK_RETRIES = 3
BROWSER_CLOSE_TIMEOUT_S = 10
MIN_HTML_LENGTH = 1_000
LOCAL_TARGET_PREFIX = "local:"
RANDOM_SOURCE = random.SystemRandom()
REALISTIC_USER_AGENTS = (
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/134.0.6998.166 Safari/537.36"
    ),
)
REALISTIC_VIEWPORTS = (
    {"width": 1366, "height": 768},
    {"width": 1440, "height": 900},
    {"width": 1536, "height": 864},
    {"width": 1600, "height": 900},
    {"width": 1728, "height": 1117},
    {"width": 1920, "height": 1080},
)


class ProxySettings(TypedDict, total=False):
    server: str
    username: str
    password: str
    bypass: str


class BrowserFingerprint(TypedDict):
    user_agent: str
    viewport: dict[str, int]
    headers: dict[str, str]


class ScraperError(RuntimeError):
    """Raised when scraping cannot produce a usable raw HTML snapshot."""


def _write_raw_html_sync(raw_dir: Path, html: str) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "index.html").write_text(html, encoding="utf-8")


def _write_local_debug_html_sync(raw_dir: Path, target_url: str) -> None:
    local_path_value = target_url.removeprefix(LOCAL_TARGET_PREFIX).strip()
    if not local_path_value:
        raise ScraperError("Local debug target path is empty")
    html = Path(local_path_value).expanduser().read_text(
        encoding="utf-8",
        errors="replace",
    )
    _write_raw_html_sync(raw_dir, html)


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


def _choose_user_agent() -> str:
    return RANDOM_SOURCE.choice(REALISTIC_USER_AGENTS)


def _choose_viewport() -> dict[str, int]:
    viewport = RANDOM_SOURCE.choice(REALISTIC_VIEWPORTS)
    return {"width": viewport["width"], "height": viewport["height"]}


def _choose_human_delay_ms() -> int:
    return RANDOM_SOURCE.randint(*HUMAN_DELAY_RANGE_MS)


def _choose_action_jitter_ms() -> int:
    return RANDOM_SOURCE.randint(*ACTION_JITTER_RANGE_MS)


def _choose_retry_backoff_ms() -> int:
    return RANDOM_SOURCE.randint(*RETRY_BACKOFF_RANGE_MS)


def _extract_chrome_major(user_agent: str) -> str:
    marker = "Chrome/"
    marker_index = user_agent.find(marker)
    if marker_index < 0:
        return "135"
    version_start = marker_index + len(marker)
    version_end = user_agent.find(".", version_start)
    if version_end < 0:
        return "135"
    major = user_agent[version_start:version_end].strip()
    return major if major.isdigit() else "135"


def _build_extra_headers(user_agent: str) -> dict[str, str]:
    chrome_major = _extract_chrome_major(user_agent)
    return {
        "Accept-Language": "en-US,en;q=0.9",
        "Sec-Ch-Ua": f'"Chromium";v="{chrome_major}", "Google Chrome";v="{chrome_major}", "Not.A/Brand";v="24"',
        "Sec-Ch-Ua-Mobile": "?0",
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Upgrade-Insecure-Requests": "1",
    }


def _build_browser_fingerprint() -> BrowserFingerprint:
    user_agent = _choose_user_agent()
    return {
        "user_agent": user_agent,
        "viewport": _choose_viewport(),
        "headers": _build_extra_headers(user_agent),
    }


def _build_context_options(fingerprint: BrowserFingerprint) -> dict[str, object]:
    viewport = fingerprint["viewport"]
    return {
        "user_agent": fingerprint["user_agent"],
        "viewport": viewport,
        "screen": viewport.copy(),
        "locale": "en-US",
        "color_scheme": "dark",
        "extra_http_headers": fingerprint["headers"],
    }


def _build_proxy_settings(proxy_url: str | None) -> ProxySettings | None:
    if proxy_url is None:
        return None
    normalized_proxy_url = proxy_url.strip()
    if not normalized_proxy_url:
        return None

    parsed = urlsplit(normalized_proxy_url)
    if not parsed.scheme or not parsed.hostname:
        return {"server": normalized_proxy_url}
    try:
        port = parsed.port
    except ValueError:
        return {"server": normalized_proxy_url}

    proxy_settings: ProxySettings = {
        "server": f"{parsed.scheme}://{parsed.hostname}:{port}"
        if port is not None
        else f"{parsed.scheme}://{parsed.hostname}",
    }
    if parsed.username:
        proxy_settings["username"] = unquote(parsed.username)
    if parsed.password:
        proxy_settings["password"] = unquote(parsed.password)
    return proxy_settings


def _build_launch_options(proxy_url: str | None) -> dict[str, object]:
    launch_options: dict[str, object] = {
        "headless": True,
        "args": ["--no-sandbox", "--disable-dev-shm-usage"],
    }
    proxy_settings = _build_proxy_settings(proxy_url)
    if proxy_settings is not None:
        launch_options["proxy"] = proxy_settings
    return launch_options


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
        raise ScraperError("Timeout: target URL unreachable") from exc


async def _wait_for_network_idle(page: object, job_id: int) -> None:
    try:
        await page.wait_for_load_state("networkidle", timeout=NETWORKIDLE_TIMEOUT_MS)
    except PlaywrightTimeoutError:
        message = "networkidle timeout, using partial DOM"
        logger.warning("%s (job_id=%s)", message, job_id)
        await _log_job_message(job_id, "warn", message)


def _find_challenge_marker(current_url: str, page_title: str, html: str) -> tuple[bool, str, str]:
    normalized_url = current_url.lower()
    normalized_title = page_title.lower()
    normalized_html = html.lower()
    candidates = (
        ("url", normalized_url),
        ("title", normalized_title),
        ("html", normalized_html),
    )
    for source, text in candidates:
        for token in CHALLENGE_PAGE_TOKENS:
            if token in text:
                return True, source, token

    # Cloudflare/Datadome scripts can be present in normal pages; treat as blocked only
    # when coupled with explicit challenge messaging in title or URL.
    soft_tokens = ("challenge-platform", "cloudflare", "datadome", "enable javascript")
    blocker_hints = ("challenge", "captcha", "verify", "just a moment", "checking your browser")
    title_or_url_has_hint = any(hint in normalized_url or hint in normalized_title for hint in blocker_hints)
    for token in soft_tokens:
        if token in normalized_html and title_or_url_has_hint:
            return True, "html", token
    return False, "", ""


async def _wait_for_real_content(page: object, job_id: int) -> None:
    human_delay_ms = _choose_human_delay_ms()
    logger.info(
        "scraper: waiting %sms for JS challenge settle (job_id=%s)",
        human_delay_ms,
        job_id,
    )
    await page.wait_for_timeout(human_delay_ms)

    for attempt in range(CHALLENGE_SETTLE_ATTEMPTS):
        current_url = str(page.url)
        page_title = await page.title()
        html = await page.content()
        marker_detected, marker_source, marker_token = _find_challenge_marker(current_url, page_title, html)
        logger.debug(
            "scraper: marker check job_id=%s attempt=%s detected=%s source=%s token=%s url=%s html_len=%s",
            job_id,
            attempt + 1,
            marker_detected,
            marker_source,
            marker_token,
            current_url[:220],
            len(html),
        )
        if not marker_detected:
            return
        if attempt == CHALLENGE_SETTLE_ATTEMPTS - 1:
            raise ScraperError("Target URL blocked by anti-bot")
        logger.info(
            "scraper: challenge markers still present, retrying settle (job_id=%s attempt=%s)",
            job_id,
            attempt + 1,
        )
        await _wait_for_network_idle(page, job_id)
        await page.wait_for_timeout(CHALLENGE_SETTLE_POLL_MS)


async def _collect_html(page: object) -> str:
    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    await page.wait_for_timeout(LAZY_LOAD_WAIT_MS)
    return await page.content()


async def _wait_action_jitter(page: object) -> None:
    await page.wait_for_timeout(_choose_action_jitter_ms())


def _is_retryable_block_error(error_message: str) -> bool:
    normalized = error_message.lower()
    return (
        "blocked by anti-bot" in normalized
        or "too small, possible bot detection" in normalized
    )


async def _safe_close_browser(browser: object, job_id: int, attempt: int) -> None:
    logger.info("scraper: closing browser (job_id=%s)", job_id)
    try:
        await asyncio.wait_for(browser.close(), timeout=BROWSER_CLOSE_TIMEOUT_S)
    except Exception as close_exc:
        logger.warning(
            "scraper: browser close failed, ignoring and continuing (job_id=%s attempt=%s error=%s)",
            job_id,
            attempt,
            str(close_exc),
        )


def _inject_font_stylesheets_in_head_sync(html: str, hrefs: list[str]) -> str:
    if not hrefs:
        return html
    links = "".join(f'<link rel="stylesheet" href="{h}">' for h in hrefs)
    lowered = html.lower()
    head_close = lowered.find("</head>")
    if head_close >= 0:
        return html[:head_close] + links + html[head_close:]
    head_open = lowered.find("<head")
    if head_open >= 0:
        gt = html.find(">", head_open)
        if gt >= 0:
            return html[: gt + 1] + links + html[gt + 1 :]
    return links + html


def _write_font_css_sync(path: Path, css_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(css_text, encoding="utf-8")


async def clean(raw_dir: Path, job_id: int, *, base_url: str | None = None) -> Path:
    """Clone raw → cleaned (BS4), self-host Google Fonts via httpx, write index + strip @import (M2.4–M2.7)."""
    cleaned_dir, html, stats, font_urls = await asyncio.to_thread(
        prepare_clean_sync, job_id=job_id, raw_dir=raw_dir, base_url=base_url
    )

    font_hrefs: list[str] = []
    if font_urls and httpx is not None:
        timeout = httpx.Timeout(ASSET_DOWNLOAD_TIMEOUT_SECONDS)
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            written_idx = 0
            for css_url in font_urls:
                rewritten = await download_google_fonts(
                    css_url=css_url,
                    fonts_dir=cleaned_dir / "assets" / "fonts",
                    client=client,
                    job_id=job_id,
                )
                if rewritten.strip():
                    rel_href = f"./assets/fonts/gfonts_{written_idx}.css"
                    dest = cleaned_dir / "assets" / "fonts" / f"gfonts_{written_idx}.css"
                    await asyncio.to_thread(_write_font_css_sync, dest, rewritten)
                    font_hrefs.append(rel_href)
                    written_idx += 1

    if font_hrefs:
        html = await asyncio.to_thread(_inject_font_stylesheets_in_head_sync, html, font_hrefs)

    result = await asyncio.to_thread(
        finalize_clean_sync, cleaned_dir, html, stats, font_urls
    )

    s = result.stats
    await _log_job_message(
        job_id, "info", f"dom_cleaner: removed tracker scripts: {s.removed_tracker_scripts}"
    )
    await _log_job_message(
        job_id, "info", f"dom_cleaner: removed tracker iframes: {s.removed_tracker_iframes}"
    )
    await _log_job_message(job_id, "info", f"dom_cleaner: removed noscript tags: {s.removed_noscripts}")
    await _log_job_message(job_id, "info", f"dom_cleaner: removed CSP meta tags: {s.removed_csp_meta}")
    await _log_job_message(
        job_id, "info", f"dom_cleaner: removed HTML comments: {s.removed_html_comments}"
    )
    await _log_job_message(
        job_id, "info", f"dom_cleaner: removed Google Fonts link tags: {s.removed_google_font_links}"
    )
    await _log_job_message(
        job_id, "info", f"dom_cleaner: stripped Google Fonts @import rules: {s.removed_font_imports}"
    )
    await _log_job_message(
        job_id, "info", f"dom_cleaner: unwrapped bdo/cite tags: {s.removed_bdo_cite}"
    )

    return result.cleaned_dir


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


async def scrape(
    job_id: int,
    target_url: str,
    *,
    proxy_url: str | None = None,
) -> Path:
    raw_dir = get_job_dir(job_id) / "raw"
    if target_url.startswith(LOCAL_TARGET_PREFIX):
        logger.info("scraper: using local debug target (job_id=%s)", job_id)
        await asyncio.to_thread(_write_local_debug_html_sync, raw_dir, target_url)
        return raw_dir

    _require_playwright()
    html: str | None = None

    for attempt in range(1, MAX_BLOCK_RETRIES + 1):
        fingerprint = _build_browser_fingerprint()
        try:
            async with async_playwright() as playwright_api:
                logger.info(
                    "scraper: launching chromium (job_id=%s attempt=%s ua=%s)",
                    job_id,
                    attempt,
                    fingerprint["user_agent"],
                )
                browser = await asyncio.wait_for(
                    playwright_api.chromium.launch(**_build_launch_options(proxy_url)),
                    timeout=30,
                )
                try:
                    logger.info("scraper: creating browser context (job_id=%s)", job_id)
                    context = await asyncio.wait_for(
                        browser.new_context(**_build_context_options(fingerprint)),
                        timeout=15,
                    )

                    logger.info("scraper: creating new page (job_id=%s)", job_id)
                    page = await asyncio.wait_for(context.new_page(), timeout=15)
                    await page.set_extra_http_headers(fingerprint["headers"])
                    try:
                        await stealth_async(page)
                    except Exception as stealth_exc:
                        logger.warning(
                            "scraper: stealth patch failed, continue without stealth (job_id=%s attempt=%s error=%s)",
                            job_id,
                            attempt,
                            str(stealth_exc),
                        )

                    await _wait_action_jitter(page)
                    logger.info("scraper: navigating to target url (job_id=%s)", job_id)
                    await _navigate(page, target_url)
                    await _wait_action_jitter(page)

                    if _is_anti_bot_redirect(target_url, page.url):
                        raise ScraperError("Target URL blocked by anti-bot")

                    logger.info("scraper: waiting for network idle (job_id=%s)", job_id)
                    await _wait_for_network_idle(page, job_id)
                    await _wait_action_jitter(page)
                    await _wait_for_real_content(page, job_id)
                    await _wait_action_jitter(page)

                    logger.info("scraper: collecting page html (job_id=%s)", job_id)
                    html = await _collect_html(page)
                    if len(html) < MIN_HTML_LENGTH:
                        raise ScraperError("Scraped HTML too small, possible bot detection")
                finally:
                    await _safe_close_browser(browser, job_id, attempt)
            if html is not None:
                break
        except ScraperError as exc:
            error_message = str(exc)
            if attempt < MAX_BLOCK_RETRIES and _is_retryable_block_error(error_message):
                backoff_ms = _choose_retry_backoff_ms()
                logger.warning(
                    "scraper: anti-bot response detected, retrying with new fingerprint "
                    "(job_id=%s attempt=%s/%s wait_ms=%s reason=%s)",
                    job_id,
                    attempt,
                    MAX_BLOCK_RETRIES,
                    backoff_ms,
                    error_message,
                )
                await asyncio.sleep(backoff_ms / 1000)
                continue
            raise
        except Exception as exc:
            logger.exception(
                "scraper: unexpected error during attempt (job_id=%s attempt=%s)",
                job_id,
                attempt,
            )
            if attempt < MAX_BLOCK_RETRIES:
                backoff_ms = _choose_retry_backoff_ms()
                await asyncio.sleep(backoff_ms / 1000)
                continue
            raise ScraperError(f"Scraper runtime error: {type(exc).__name__}") from exc

    if html is None:
        raise ScraperError("Target URL blocked by anti-bot")

    logger.info("scraper: rewriting asset urls (job_id=%s)", job_id)
    rewrite_result = await _rewrite_scraped_assets(
        job_id=job_id,
        target_url=target_url,
        raw_dir=raw_dir,
        html=html,
    )
    logger.info("scraper: writing raw html to disk (job_id=%s)", job_id)
    await asyncio.to_thread(_write_raw_html_sync, raw_dir, rewrite_result.html)
    return raw_dir


async def module_scraper(
    job_id: int,
    target_url: str,
    proxy_url: str | None = None,
) -> None:
    logger.info("module_scraper: start (job_id=%s)", job_id)
    raw_dir = await scrape(job_id, target_url, proxy_url=proxy_url)
    logger.info("module_scraper: raw_dir=%s job_id=%s", raw_dir.as_posix(), job_id)
    await clean(raw_dir, job_id, base_url=target_url)
    logger.info("module_scraper: done (job_id=%s)", job_id)
