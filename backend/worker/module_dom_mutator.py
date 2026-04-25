import hashlib
import logging
import re
from pathlib import Path
from typing import Final

from backend.database import get_connection

logger = logging.getLogger(__name__)

# PRD M3.1: exact extraction regex (no CSS parsers).
CSS_SELECTOR_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![\"'])([.#][\w-]+)(?=\s*[{,:\[])"
)


def _load_exclusion_prefixes() -> tuple[str, ...]:
    """
    Loads settings.js_class_exclusion_prefixes (CSV).
    Matching is case-insensitive by design (see task note).
    """
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            ("js_class_exclusion_prefixes",),
        ).fetchone()
        raw = str(row["value"]) if row is not None else ""
    finally:
        conn.close()

    prefixes: list[str] = []
    for part in raw.split(","):
        p = part.strip()
        if not p:
            continue
        prefixes.append(p.lower())
    return tuple(prefixes)


def _is_excluded(token: str, exclusion_prefixes: tuple[str, ...]) -> bool:
    """
    token is full selector token with leading '.' or '#'.
    Exclusion prefixes apply to the selector name part only, case-insensitive.
    """
    name = token[1:] if token[:1] in ".#" else token
    name_l = name.lower()
    return any(name_l.startswith(prefix) for prefix in exclusion_prefixes)


def _alias_for_token(token: str, used_aliases: set[str]) -> str:
    """
    Deterministic alias generation: 'x' + 4 hex chars.
    Collision resolution is also deterministic using an incrementing salt.
    """
    for salt in range(10_000):
        payload = f"{token}|{salt}".encode("utf-8")
        suffix = hashlib.md5(payload).hexdigest()[:4]  # nosec - not for security
        alias = f"x{suffix}"
        if alias not in used_aliases:
            used_aliases.add(alias)
            return alias
    raise RuntimeError("Unable to generate a unique alias after 10k attempts")


def build_selector_map(css_files: list[Path]) -> dict[str, str]:
    """
    Build a selector alias map from CSS files only.

    - Extracts only class (.foo) and id (#bar) selector tokens using PRD regex.
    - Filters tokens by settings.js_class_exclusion_prefixes (CSV), case-insensitive.
    - Generates deterministic aliases (x + 4 hex chars), resolves collisions.
    - Does NOT modify any files.

    Returns:
      {".order-btn": ".x8f9a", "#hero": "#x3a9d"}
    """
    exclusion_prefixes = _load_exclusion_prefixes()

    tokens: set[str] = set()
    for css_file in css_files:
        try:
            css_text = css_file.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            logger.warning("CSS read failed (%s): %s", css_file, exc)
            continue

        try:
            matches = CSS_SELECTOR_PATTERN.findall(css_text)
        except re.error as exc:
            # EC-06: regex failure on minified CSS should not break pipeline.
            logger.warning("CSS parse failed: %s (%s)", css_file.name, exc)
            continue

        tokens.update(matches)

    # Stable output within a run (and across runs given same inputs/settings).
    ordered_tokens = sorted(tokens)

    selector_map: dict[str, str] = {}
    used_aliases: set[str] = set()

    for token in ordered_tokens:
        if _is_excluded(token, exclusion_prefixes):
            continue

        prefix = token[0]  # '.' or '#'
        alias = _alias_for_token(token, used_aliases)
        selector_map[token] = f"{prefix}{alias}"

    return selector_map

