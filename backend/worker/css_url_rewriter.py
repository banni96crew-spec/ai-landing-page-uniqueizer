import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from backend.worker.asset_rewriter import _resolve_and_download_async

CSS_URL_PATTERN = re.compile(r"""url\(\s*(['"]?)([^'")]+)\1\s*\)""", re.IGNORECASE)


def _build_css_relative_url(*, css_file_path: Path, assets_dir: Path, filename: str) -> str:
    target_path = assets_dir / filename
    relative_path = os.path.relpath(target_path, start=css_file_path.parent)
    return relative_path.replace("\\", "/")


async def rewrite_css_urls(
    *,
    css_text: str,
    css_file_base_url: str,
    css_file_path: Path,
    assets_dir: Path,
    url_cache: dict[str, str],
    used_filenames: dict[str, str],
    client: Any,
    job_id: int,
) -> str:
    base_scheme = urlparse(css_file_base_url).scheme or "https"
    parts: list[str] = []
    last = 0

    for match in CSS_URL_PATTERN.finditer(css_text):
        parts.append(css_text[last : match.start()])
        quote = match.group(1)
        url_value = match.group(2).strip()
        result = await _resolve_and_download_async(
            url_value=url_value,
            base_url=css_file_base_url,
            base_scheme=base_scheme,
            assets_dir=assets_dir,
            url_cache=url_cache,
            used_filenames=used_filenames,
            client=client,
            job_id=job_id,
        )
        rewritten_url = result.rewritten_url
        if result.filename is not None:
            rewritten_url = _build_css_relative_url(
                css_file_path=css_file_path,
                assets_dir=assets_dir,
                filename=result.filename,
            )
        parts.append(f"url({quote}{rewritten_url}{quote})")
        last = match.end()

    parts.append(css_text[last:])
    return "".join(parts)
