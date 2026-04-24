import asyncio
import logging
import re
from pathlib import Path
from urllib.parse import urlparse

try:
    import httpx
except ModuleNotFoundError:  # pragma: no cover - fallback for test environments
    httpx = None  # type: ignore[assignment]

from backend.database import get_connection, log_message

logger = logging.getLogger(__name__)


def _write_bytes_sync(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _log_job_message_sync(job_id: int, level: str, message: str) -> None:
    conn = get_connection()
    try:
        log_message(conn, job_id, level, message)
    finally:
        conn.close()


async def _log_job_message(job_id: int, level: str, message: str) -> None:
    await asyncio.to_thread(_log_job_message_sync, job_id, level, message)


async def download_google_fonts(
    *, css_url: str, fonts_dir: Path, client: "httpx.AsyncClient", job_id: int
) -> str:
    """
    PRD §3.3 / M2.5:
    - fetch CSS from fonts.googleapis.com with Windows UA
    - extract .woff2 gstatic URLs
    - download into cleaned/assets/fonts/
    - rewrite CSS URLs to ./assets/fonts/{filename}
    """
    try:
        if httpx is None:
            raise RuntimeError("httpx package is not installed")

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            )
        }
        resp = await client.get(css_url, headers=headers, follow_redirects=True)
        if resp.status_code != 200:
            raise RuntimeError(f"fonts css http {resp.status_code}")
        css_text = resp.text

        urls = re.findall(r"url\((https://fonts\.gstatic\.com/[^)]+\.woff2)\)", css_text)
        if not urls:
            return css_text

        for font_url in sorted(set(urls)):
            filename = Path(urlparse(font_url).path).name
            if not filename:
                filename = f"font_{abs(hash(font_url))}.woff2"

            font_resp = await client.get(font_url, headers=headers, follow_redirects=True)
            if font_resp.status_code != 200:
                message = (
                    f"google_fonts: failed to download font (http {font_resp.status_code}): {font_url}"
                )
                logger.warning("%s (job_id=%s)", message, job_id)
                await _log_job_message(job_id, "warn", message)
                continue

            await asyncio.to_thread(_write_bytes_sync, fonts_dir / filename, font_resp.content)
            css_text = css_text.replace(font_url, f"./assets/fonts/{filename}")

        return css_text
    except Exception as exc:
        message = f"google_fonts: download failed for css={css_url}: {exc}"
        logger.warning("%s (job_id=%s)", message, job_id)
        await _log_job_message(job_id, "warn", message)
        return ""
