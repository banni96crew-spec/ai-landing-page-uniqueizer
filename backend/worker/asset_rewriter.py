import hashlib
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from backend.config import ASSET_MAX_SIZE_BYTES

logger = logging.getLogger(__name__)

REWRITABLE_ATTRS = {"src", "href", "action", "data-src", "data-href"}
SRCSET_ATTRS = {"srcset"}
SKIP_PREFIXES = ("data:", "javascript:", "mailto:", "tel:", "#")

_ATTR_RE_TEMPLATE = r"""(?P<prefix>\b{attr}\s*=\s*)(?P<quote>["'])(?P<value>.*?)(?P=quote)"""
_ATTR_FLAGS = re.IGNORECASE | re.DOTALL


@dataclass(frozen=True)
class _DownloadResult:
    rewritten_url: str
    abs_url: str | None = None
    filename: str | None = None


def _should_skip(url_value: str) -> bool:
    candidate = url_value.strip()
    if not candidate:
        return True
    lowered = candidate.lower()
    return lowered.startswith(SKIP_PREFIXES)


def _resolve_abs_url(url_value: str, *, base_url: str, base_scheme: str) -> str | None:
    raw = url_value.strip()
    if not raw or _should_skip(raw):
        return None

    lowered = raw.lower()
    if lowered.startswith("//"):
        return f"{base_scheme}:{raw}"
    if lowered.startswith(("http://", "https://")):
        return raw
    return urljoin(base_url, raw)


def _pick_filename(abs_url: str) -> str:
    parsed = urlparse(abs_url)
    name = Path(parsed.path).name
    if name and "." in name:
        return name
    digest = hashlib.md5(abs_url.encode("utf-8")).hexdigest()[:8]
    return f"{digest}.bin"


def _dedupe_filename(
    *,
    filename: str,
    abs_url: str,
    assets_dir: Path,
    used_filenames: dict[str, str],
) -> str:
    target = assets_dir / filename
    stem = Path(filename).stem
    suffix = Path(filename).suffix
    counter = 1
    while True:
        owner = used_filenames.get(filename)
        if owner == abs_url:
            return filename
        if not target.exists() and owner is None:
            return filename
        filename = f"{stem}_{counter}{suffix}"
        target = assets_dir / filename
        counter += 1


async def _stream_to_file(
    *,
    response: Any,
    target_path: Path,
    job_id: int,
    abs_url: str,
) -> bool:
    content_length = response.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > ASSET_MAX_SIZE_BYTES:
                logger.warning(
                    "Asset too large (content-length>%sB), skipping: %s (job_id=%s)",
                    ASSET_MAX_SIZE_BYTES,
                    abs_url,
                    job_id,
                )
                return False
        except ValueError:
            pass

    total = 0
    chunks: list[bytes] = []
    async for chunk in response.aiter_bytes(chunk_size=65536):
        total += len(chunk)
        if total > ASSET_MAX_SIZE_BYTES:
            logger.warning(
                "Asset too large (>%sB), skipping: %s (job_id=%s)",
                ASSET_MAX_SIZE_BYTES,
                abs_url,
                job_id,
            )
            return False
        chunks.append(chunk)

    target_path.write_bytes(b"".join(chunks))
    return True


async def _resolve_and_download_async(
    *,
    url_value: str,
    base_url: str,
    base_scheme: str,
    assets_dir: Path,
    url_cache: dict[str, str],
    used_filenames: dict[str, str],
    client: Any,
    job_id: int,
) -> _DownloadResult:
    if _should_skip(url_value):
        return _DownloadResult(rewritten_url=url_value)

    abs_url = _resolve_abs_url(url_value, base_url=base_url, base_scheme=base_scheme)
    if abs_url is None:
        return _DownloadResult(rewritten_url=url_value)

    cached = url_cache.get(abs_url)
    if cached:
        return _DownloadResult(
            rewritten_url=f"./assets/{cached}",
            abs_url=abs_url,
            filename=cached,
        )

    assets_dir.mkdir(parents=True, exist_ok=True)
    desired = _pick_filename(abs_url)
    final_name = _dedupe_filename(
        filename=desired,
        abs_url=abs_url,
        assets_dir=assets_dir,
        used_filenames=used_filenames,
    )
    target_path = assets_dir / final_name

    try:
        async with client.stream("GET", abs_url) as response:
            if getattr(response, "status_code", None) != 200:
                logger.warning(
                    "Asset download failed (status=%s): %s (job_id=%s)",
                    getattr(response, "status_code", None),
                    abs_url,
                    job_id,
                )
                return _DownloadResult(rewritten_url=url_value)

            ok = await _stream_to_file(
                response=response, target_path=target_path, job_id=job_id, abs_url=abs_url
            )
            if not ok:
                return _DownloadResult(rewritten_url=url_value)

        url_cache[abs_url] = final_name
        used_filenames[final_name] = abs_url
        return _DownloadResult(
            rewritten_url=f"./assets/{final_name}",
            abs_url=abs_url,
            filename=final_name,
        )
    except Exception as exc:
        logger.warning(
            "Asset download failed: %s → %s (job_id=%s)",
            abs_url,
            exc,
            job_id,
        )
        return _DownloadResult(rewritten_url=url_value)


async def rewrite_srcset(
    *,
    srcset_value: str,
    base_url: str,
    base_scheme: str,
    assets_dir: Path,
    url_cache: dict[str, str],
    used_filenames: dict[str, str],
    client: Any,
    job_id: int,
) -> str:
    parts = srcset_value.split(",")
    out: list[str] = []
    for part in parts:
        tokens = part.strip().split()
        if not tokens:
            continue
        url_part = tokens[0]
        descriptor = tokens[1] if len(tokens) > 1 else ""
        result = await _resolve_and_download_async(
            url_value=url_part,
            base_url=base_url,
            base_scheme=base_scheme,
            assets_dir=assets_dir,
            url_cache=url_cache,
            used_filenames=used_filenames,
            client=client,
            job_id=job_id,
        )
        out.append(f"{result.rewritten_url} {descriptor}".strip())
    return ", ".join(out)


async def rewrite_asset_urls(
    *,
    html: str,
    base_url: str,
    raw_dir: Path,
    client: Any,
    job_id: int,
) -> str:
    parsed = urlparse(base_url)
    base_scheme = parsed.scheme or "https"
    assets_dir = raw_dir / "assets"

    url_cache: dict[str, str] = {}
    used_filenames: dict[str, str] = {}

    out = html

    async def _replace_attr(match: re.Match, attr_name: str) -> str:
        prefix = match.group("prefix")
        quote = match.group("quote")
        value = match.group("value")
        result = await _resolve_and_download_async(
            url_value=value,
            base_url=base_url,
            base_scheme=base_scheme,
            assets_dir=assets_dir,
            url_cache=url_cache,
            used_filenames=used_filenames,
            client=client,
            job_id=job_id,
        )
        return f"{prefix}{quote}{result.rewritten_url}{quote}"

    async def _replace_srcset(match: re.Match) -> str:
        prefix = match.group("prefix")
        quote = match.group("quote")
        value = match.group("value")
        rewritten = await rewrite_srcset(
            srcset_value=value,
            base_url=base_url,
            base_scheme=base_scheme,
            assets_dir=assets_dir,
            url_cache=url_cache,
            used_filenames=used_filenames,
            client=client,
            job_id=job_id,
        )
        return f"{prefix}{quote}{rewritten}{quote}"

    # Replace normal URL attributes.
    for attr in sorted(REWRITABLE_ATTRS):
        pattern = re.compile(_ATTR_RE_TEMPLATE.format(attr=re.escape(attr)), _ATTR_FLAGS)

        parts: list[str] = []
        last = 0
        for m in pattern.finditer(out):
            parts.append(out[last : m.start()])
            parts.append(await _replace_attr(m, attr))
            last = m.end()
        parts.append(out[last:])
        out = "".join(parts)

    # Replace srcset separately (needs parsing of list).
    for attr in sorted(SRCSET_ATTRS):
        pattern = re.compile(_ATTR_RE_TEMPLATE.format(attr=re.escape(attr)), _ATTR_FLAGS)
        parts = []
        last = 0
        for m in pattern.finditer(out):
            parts.append(out[last : m.start()])
            parts.append(await _replace_srcset(m))
            last = m.end()
        parts.append(out[last:])
        out = "".join(parts)

    return out

