import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ModuleNotFoundError:  # pragma: no cover - fallback for test environments
    BeautifulSoup = None  # type: ignore[assignment]

from backend.config import get_job_dir


@dataclass(frozen=True)
class DomCleanStats:
    removed_scripts: int
    removed_noscripts: int
    removed_iframes: int
    removed_csp_meta: int
    removed_inline_handlers: int


@dataclass(frozen=True)
class DomCleanResult:
    cleaned_dir: Path
    index_html_path: Path
    stats: DomCleanStats


def _is_csp_meta(tag: object) -> bool:
    if getattr(tag, "name", None) != "meta":
        return False
    attrs = getattr(tag, "attrs", None) or {}
    http_equiv = attrs.get("http-equiv") or attrs.get("http_equiv")
    if http_equiv is None:
        return False
    return str(http_equiv).strip().lower() == "content-security-policy"


def _clean_html_sync(html: str) -> tuple[str, DomCleanStats]:
    if BeautifulSoup is None:
        raise RuntimeError("beautifulsoup4 package is not installed")
    soup = BeautifulSoup(html, "lxml")

    removed_scripts = 0
    for tag in soup.find_all("script"):
        tag.decompose()
        removed_scripts += 1

    removed_noscripts = 0
    for tag in soup.find_all("noscript"):
        tag.decompose()
        removed_noscripts += 1

    removed_iframes = 0
    for tag in soup.find_all("iframe"):
        tag.decompose()
        removed_iframes += 1

    removed_csp_meta = 0
    for tag in soup.find_all(_is_csp_meta):
        tag.decompose()
        removed_csp_meta += 1

    removed_inline_handlers = 0
    for tag in soup.find_all(True):
        attrs = getattr(tag, "attrs", None)
        if not isinstance(attrs, dict):
            continue
        to_remove = [k for k in attrs.keys() if str(k).lower().startswith("on")]
        for k in to_remove:
            attrs.pop(k, None)
            removed_inline_handlers += 1

    cleaned_html = str(soup)
    stats = DomCleanStats(
        removed_scripts=removed_scripts,
        removed_noscripts=removed_noscripts,
        removed_iframes=removed_iframes,
        removed_csp_meta=removed_csp_meta,
        removed_inline_handlers=removed_inline_handlers,
    )
    return cleaned_html, stats


def _clone_and_clean_sync(*, job_id: int, raw_dir: Path) -> DomCleanResult:
    expected_raw_dir = get_job_dir(job_id) / "raw"
    if raw_dir != expected_raw_dir:
        raise ValueError(f"raw_dir must be {expected_raw_dir}, got {raw_dir}")

    raw_index = raw_dir / "index.html"
    if not raw_index.exists():
        raise FileNotFoundError(str(raw_index))

    cleaned_dir = get_job_dir(job_id) / "cleaned"
    if cleaned_dir.exists():
        shutil.rmtree(cleaned_dir)

    shutil.copytree(raw_dir, cleaned_dir)

    raw_html = raw_index.read_text(encoding="utf-8")
    cleaned_html, stats = _clean_html_sync(raw_html)

    cleaned_index = cleaned_dir / "index.html"
    cleaned_index.write_text(cleaned_html, encoding="utf-8")

    return DomCleanResult(cleaned_dir=cleaned_dir, index_html_path=cleaned_index, stats=stats)


async def clean_job_html(job_id: int, raw_dir: Path) -> DomCleanResult:
    """Read raw/index.html, create cleaned/, return cleaned_dir + stats."""
    return await asyncio.to_thread(_clone_and_clean_sync, job_id=job_id, raw_dir=raw_dir)

