import asyncio
import hashlib
import logging
import random
import re
import shutil
import time
from pathlib import Path
from typing import Final

from bs4 import BeautifulSoup

from backend.config import get_job_dir
from backend.database import get_connection, log_message
from backend.worker.mutator_js_regex import mutate_js_string

logger = logging.getLogger(__name__)

# PRD M3.1: exact extraction regex (no CSS parsers).
CSS_SELECTOR_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![\"'])([.#][\w-]+)(?=\s*[{,:\[])"
)
INTER_TAG_WHITESPACE_PATTERN: Final[re.Pattern[str]] = re.compile(r">\s+<")
NOISE_NODE_COUNT: Final[int] = 3
INTER_TAG_WHITESPACE_CHOICES: Final[tuple[str, ...]] = ("\n", "\n\n", "\n  ", " ")


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


def _log_job_message_sync(job_id: int, level: str, message: str) -> None:
    conn = get_connection()
    try:
        log_message(conn, job_id, level, message)
    finally:
        conn.close()


def _split_selector_map(
    selector_map: dict[str, str],
) -> tuple[dict[str, str], dict[str, str]]:
    class_map: dict[str, str] = {}
    id_map: dict[str, str] = {}

    for source, target in selector_map.items():
        if source.startswith(".") and target.startswith("."):
            class_map[source[1:]] = target[1:]
        elif source.startswith("#") and target.startswith("#"):
            id_map[source[1:]] = target[1:]

    return class_map, id_map


def _replace_css_selectors(css_text: str, selector_map: dict[str, str]) -> str:
    def replace_match(match: re.Match[str]) -> str:
        return selector_map.get(match.group(1), match.group(1))

    return CSS_SELECTOR_PATTERN.sub(replace_match, css_text)


def _randomize_inter_tag_whitespace(html_text: str) -> str:
    def replace_match(match: re.Match[str]) -> str:
        _ = match
        return f">{random.choice(INTER_TAG_WHITESPACE_CHOICES)}<"

    return INTER_TAG_WHITESPACE_PATTERN.sub(replace_match, html_text)


def _random_noise_alias(used_aliases: set[str]) -> str:
    for _ in range(10_000):
        alias = f"x{random.randint(0, 0xFFFF):04x}"
        if alias not in used_aliases:
            used_aliases.add(alias)
            return alias
    raise RuntimeError("Unable to generate a unique noise alias after 10k attempts")


def _noise_aliases(selector_map: dict[str, str]) -> list[str]:
    used_aliases = {value[1:] for value in selector_map.values() if value[:1] in ".#"}
    aliases: list[str] = []
    for _ in range(NOISE_NODE_COUNT):
        aliases.append(_random_noise_alias(used_aliases))
    return aliases


def inject_dom_noise(soup: BeautifulSoup, selector_map: dict[str, str]) -> None:
    if soup.head is None:
        head = soup.new_tag("head")
        if soup.html is not None:
            soup.html.insert(0, head)
        else:
            soup.insert(0, head)

    target = soup.body or soup
    aliases = _noise_aliases(selector_map)
    for alias in aliases:
        noise_node = soup.new_tag("div")
        noise_node["class"] = [alias]
        noise_node["aria-hidden"] = "true"
        target.append(noise_node)

    style_tag = soup.new_tag("style")
    style_tag.string = "\n".join(
        f".{alias} {{ display: none; opacity: 0; }}" for alias in aliases
    )
    soup.head.append(style_tag)


def _mutate_html_file(
    html_file: Path,
    class_map: dict[str, str],
    id_map: dict[str, str],
    selector_map: dict[str, str],
) -> None:
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8", errors="replace"), "lxml")

    for tag in soup.find_all(True):
        class_values = tag.get("class")
        if isinstance(class_values, list):
            tag["class"] = [
                class_map.get(str(class_name), str(class_name))
                for class_name in class_values
            ]

        tag_id = tag.get("id")
        if isinstance(tag_id, str) and tag_id in id_map:
            tag["id"] = id_map[tag_id]

    inject_dom_noise(soup, selector_map)
    html_file.write_text(_randomize_inter_tag_whitespace(str(soup)), encoding="utf-8")


def _mutate_css_files(
    mutated_dir: Path,
    selector_map: dict[str, str],
    job_id: int,
) -> None:
    for css_file in mutated_dir.rglob("*.css"):
        try:
            css_text = css_file.read_text(encoding="utf-8", errors="replace")
            mutated_css = _replace_css_selectors(css_text, selector_map)
            if mutated_css != css_text:
                css_file.write_text(mutated_css, encoding="utf-8")
        except (OSError, re.error) as exc:
            message = f"CSS parse failed: {css_file.name}"
            logger.warning("%s (%s)", message, exc)
            _log_job_message_sync(job_id, "warn", message)


def _mutate_js_files(
    mutated_dir: Path,
    class_map: dict[str, str],
    id_map: dict[str, str],
    job_id: int,
) -> None:
    js_paths = list(mutated_dir.rglob("*.js"))
    logger.info("dom_mutator: %d .js files job_id=%s", len(js_paths), job_id)
    for js_file in js_paths:
        try:
            t_js = time.perf_counter()
            js_text = js_file.read_text(encoding="utf-8", errors="replace")
            logger.info(
                "dom_mutator: js %s (%d bytes) job_id=%s",
                js_file.relative_to(mutated_dir).as_posix(),
                len(js_text),
                job_id,
            )
            mutated_js = mutate_js_string(js_text, class_map, id_map)
            logger.info(
                "dom_mutator: js %s done in %.2fs job_id=%s",
                js_file.name,
                time.perf_counter() - t_js,
                job_id,
            )
            if mutated_js != js_text:
                js_file.write_text(mutated_js, encoding="utf-8")
        except OSError as exc:
            message = f"JS mutation failed: {js_file.name}"
            logger.warning("%s (%s)", message, exc)
            _log_job_message_sync(job_id, "warn", message)


def apply_mutations(
    mutated_dir: Path,
    selector_map: dict[str, str],
    job_id: int,
) -> None:
    class_map, id_map = _split_selector_map(selector_map)
    logger.info(
        "dom_mutator: apply_mutations class=%d id=%d job_id=%s",
        len(class_map),
        len(id_map),
        job_id,
    )

    html_file = mutated_dir / "index.html"
    t0 = time.perf_counter()
    logger.info("dom_mutator: mutating index.html job_id=%s", job_id)
    _mutate_html_file(html_file, class_map, id_map, selector_map)
    logger.info(
        "dom_mutator: index.html done in %.2fs job_id=%s",
        time.perf_counter() - t0,
        job_id,
    )
    _mutate_css_files(mutated_dir, selector_map, job_id)
    _mutate_js_files(mutated_dir, class_map, id_map, job_id)


def mutate_cleaned_tree(job_id: int) -> Path:
    t0 = time.perf_counter()
    logger.info("dom_mutator: start job_id=%s", job_id)
    job_dir = get_job_dir(job_id)
    cleaned_dir = job_dir / "cleaned"
    mutated_dir = job_dir / "mutated"

    if not cleaned_dir.is_dir():
        raise FileNotFoundError(f"Cleaned directory missing: {cleaned_dir}")

    if mutated_dir.exists():
        shutil.rmtree(mutated_dir)
    logger.info(
        "dom_mutator: copytree %s -> %s", cleaned_dir.as_posix(), mutated_dir.as_posix()
    )
    shutil.copytree(cleaned_dir, mutated_dir)
    logger.info("dom_mutator: copytree done in %.2fs", time.perf_counter() - t0)

    t1 = time.perf_counter()
    css_files = list(mutated_dir.rglob("*.css"))
    logger.info("dom_mutator: %d css files, building selector map", len(css_files))
    selector_map = build_selector_map(css_files)
    logger.info(
        "dom_mutator: selector_map %d entries in %.2fs",
        len(selector_map),
        time.perf_counter() - t1,
    )

    t2 = time.perf_counter()
    apply_mutations(mutated_dir, selector_map, job_id)
    logger.info(
        "dom_mutator: apply_mutations done in %.2fs (total %.2fs)",
        time.perf_counter() - t2,
        time.perf_counter() - t0,
    )
    return mutated_dir


async def module_dom_mutator(job_id: int) -> None:
    logger.info("module_dom_mutator: await to_thread job_id=%s", job_id)
    await asyncio.to_thread(mutate_cleaned_tree, job_id)
    logger.info("module_dom_mutator: finished job_id=%s", job_id)

