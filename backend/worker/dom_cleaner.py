import asyncio
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlparse

try:
    from bs4 import BeautifulSoup
    from bs4.element import Comment
except ModuleNotFoundError:  # pragma: no cover - fallback for test environments
    BeautifulSoup = None  # type: ignore[assignment]
    Comment = None  # type: ignore[assignment]

from backend.config import get_job_dir

# PRD §3.3 / clean() — exact host list for tracker matching.
TRACKER_DOMAINS: tuple[str, ...] = (
    "google-analytics.com",
    "googletagmanager.com",
    "connect.facebook.net",
    "pixel.facebook.com",
    "facebook.net",
    "hotjar.com",
    "mc.yandex.ru",
    "analytics.tiktok.com",
)

_GOOGLE_FONTS_HOST = "fonts.googleapis.com"

_GOOGLE_FONT_IMPORT_PATTERN = re.compile(
    r"@import[^;]*fonts\.googleapis\.com[^;]*;",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class DomCleanStats:
    removed_tracker_scripts: int
    removed_tracker_iframes: int
    removed_noscripts: int
    removed_csp_meta: int
    removed_html_comments: int
    removed_google_font_links: int
    removed_font_imports: int
    removed_bdo_cite: int


@dataclass(frozen=True)
class DomCleanResult:
    cleaned_dir: Path
    index_html_path: Path
    stats: DomCleanStats
    google_font_css_urls: tuple[str, ...] = field(default_factory=tuple)


def _is_csp_meta(tag: object) -> bool:
    if getattr(tag, "name", None) != "meta":
        return False
    attrs = getattr(tag, "attrs", None) or {}
    http_equiv = attrs.get("http-equiv") or attrs.get("http_equiv")
    if http_equiv is None:
        return False
    return str(http_equiv).strip().lower() == "content-security-policy"


def _hostname_is_tracker(hostname: str) -> bool:
    host = (hostname or "").lower()
    if not host:
        return False
    for domain in TRACKER_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
    return False


def _resolve_url(raw: str | None, base_url: str) -> str | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    joined = urljoin(base_url, s)
    parsed = urlparse(joined)
    if not parsed.scheme or parsed.scheme in ("javascript", "mailto", "data"):
        return None
    return joined


def _effective_base_url(soup: object, explicit: str | None) -> str:
    if explicit and explicit.strip():
        return explicit.strip()
    base_tag = getattr(soup, "find", lambda *_a, **_k: None)("base", href=True)
    if base_tag and base_tag.get("href"):
        return str(base_tag["href"]).strip()
    return "https://127.0.0.1/"


def _rel_is_stylesheet(rel_val: object) -> bool:
    if rel_val is None:
        return False
    if isinstance(rel_val, (list, tuple)):
        parts = [str(p).strip().lower() for p in rel_val if p is not None]
    else:
        parts = str(rel_val).lower().split()
    return "stylesheet" in parts


def _href_is_google_fonts_css(href: str, base_url: str) -> str | None:
    resolved = _resolve_url(href, base_url)
    if not resolved:
        return None
    parsed = urlparse(resolved)
    host = (parsed.hostname or "").lower()
    if host == _GOOGLE_FONTS_HOST or host.endswith("." + _GOOGLE_FONTS_HOST):
        return resolved
    return None


def _src_points_to_tracker(src: str | None, base_url: str) -> bool:
    resolved = _resolve_url(src, base_url)
    if not resolved:
        return False
    parsed = urlparse(resolved)
    return _hostname_is_tracker(parsed.hostname or "")


def _strip_google_font_imports(css_text: str) -> tuple[str, int]:
    matches = _GOOGLE_FONT_IMPORT_PATTERN.findall(css_text)
    new_text = _GOOGLE_FONT_IMPORT_PATTERN.sub("", css_text)
    return new_text, len(matches)


def _clean_html_sync(html: str, base_url: str | None) -> tuple[str, DomCleanStats, tuple[str, ...]]:
    if BeautifulSoup is None or Comment is None:
        raise RuntimeError("beautifulsoup4 package is not installed")
    soup = BeautifulSoup(html, "lxml")
    effective_base = _effective_base_url(soup, base_url)

    removed_tracker_scripts = 0
    for tag in soup.find_all("script"):
        if tag.get("src") and _src_points_to_tracker(tag.get("src"), effective_base):
            tag.decompose()
            removed_tracker_scripts += 1

    removed_tracker_iframes = 0
    for tag in soup.find_all("iframe"):
        if tag.get("src") and _src_points_to_tracker(tag.get("src"), effective_base):
            tag.decompose()
            removed_tracker_iframes += 1

    removed_noscripts = 0
    for tag in soup.find_all("noscript"):
        tag.decompose()
        removed_noscripts += 1

    removed_csp_meta = 0
    for tag in soup.find_all(_is_csp_meta):
        tag.decompose()
        removed_csp_meta += 1

    removed_html_comments = 0
    for c in soup.find_all(string=lambda t: isinstance(t, Comment)):
        c.extract()
        removed_html_comments += 1

    google_font_css_urls: list[str] = []
    removed_google_font_links = 0
    for tag in soup.find_all("link", href=True):
        if not _rel_is_stylesheet(tag.get("rel")):
            continue
        abs_css = _href_is_google_fonts_css(str(tag["href"]), effective_base)
        if abs_css:
            google_font_css_urls.append(abs_css)
            tag.decompose()
            removed_google_font_links += 1

    removed_bdo_cite = 0
    for name in ("bdo", "cite"):
        for tag in list(soup.find_all(name)):
            removed_bdo_cite += 1
            tag.unwrap()

    stats = DomCleanStats(
        removed_tracker_scripts=removed_tracker_scripts,
        removed_tracker_iframes=removed_tracker_iframes,
        removed_noscripts=removed_noscripts,
        removed_csp_meta=removed_csp_meta,
        removed_html_comments=removed_html_comments,
        removed_google_font_links=removed_google_font_links,
        removed_font_imports=0,
        removed_bdo_cite=removed_bdo_cite,
    )
    return str(soup), stats, tuple(google_font_css_urls)


def _write_index_and_strip_css_imports_sync(cleaned_dir: Path, index_html: str) -> int:
    (cleaned_dir / "index.html").write_text(index_html, encoding="utf-8")
    total_imports = 0
    for css_path in cleaned_dir.rglob("*.css"):
        text = css_path.read_text(encoding="utf-8", errors="replace")
        new_text, n = _strip_google_font_imports(text)
        total_imports += n
        if n:
            css_path.write_text(new_text, encoding="utf-8")
    return total_imports


def prepare_clean_sync(*, job_id: int, raw_dir: Path, base_url: str | None) -> tuple[Path, str, DomCleanStats, tuple[str, ...]]:
    """Clone raw → cleaned, run BS4 hygiene, return HTML before index write + font downloads."""
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
    cleaned_html, stats, google_font_css_urls = _clean_html_sync(raw_html, base_url)
    return cleaned_dir, cleaned_html, stats, google_font_css_urls


def finalize_clean_sync(
    cleaned_dir: Path,
    index_html: str,
    stats_partial: DomCleanStats,
    google_font_css_urls: tuple[str, ...],
) -> DomCleanResult:
    removed_font_imports = _write_index_and_strip_css_imports_sync(cleaned_dir, index_html)
    stats = DomCleanStats(
        removed_tracker_scripts=stats_partial.removed_tracker_scripts,
        removed_tracker_iframes=stats_partial.removed_tracker_iframes,
        removed_noscripts=stats_partial.removed_noscripts,
        removed_csp_meta=stats_partial.removed_csp_meta,
        removed_html_comments=stats_partial.removed_html_comments,
        removed_google_font_links=stats_partial.removed_google_font_links,
        removed_font_imports=removed_font_imports,
        removed_bdo_cite=stats_partial.removed_bdo_cite,
    )
    cleaned_index = cleaned_dir / "index.html"
    return DomCleanResult(
        cleaned_dir=cleaned_dir,
        index_html_path=cleaned_index,
        stats=stats,
        google_font_css_urls=google_font_css_urls,
    )


def _clone_and_clean_sync(*, job_id: int, raw_dir: Path, base_url: str | None) -> DomCleanResult:
    cleaned_dir, html, stats, urls = prepare_clean_sync(job_id=job_id, raw_dir=raw_dir, base_url=base_url)
    return finalize_clean_sync(cleaned_dir, html, stats, urls)


async def clean_job_html(
    job_id: int, raw_dir: Path, *, base_url: str | None = None
) -> DomCleanResult:
    """Read raw/index.html, create cleaned/, return cleaned_dir + stats."""
    return await asyncio.to_thread(_clone_and_clean_sync, job_id=job_id, raw_dir=raw_dir, base_url=base_url)
