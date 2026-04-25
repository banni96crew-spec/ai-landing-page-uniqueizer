import asyncio
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from bs4 import BeautifulSoup
from bs4.element import Tag

from backend.config import get_job_dir

SYSTEM_PROMPT: Final[str] = """
You are an expert direct response marketer and copywriter specializing in traffic arbitrage.
RULES:
- Rewrite text: preserve meaning, completely change lexicon (Reframe, Clarify, Amplify)
- Preserve ALL HTML tags within the text fragment unchanged
- Keep output length within ±10% of input character count
- Tone: Engaging, Empathetic, Persuasive. Zero robotic clichés.
- Return ONLY the rewritten fragment, no explanations.
"""
TEXT_NODES_SELECTOR: Final[tuple[str, ...]] = (
    "h1", "h2", "h3", "h4", "h5", "h6", "p", "button", "li", "span",
)
TEXT_NODE_MIN_LENGTH: Final[int] = 10
BATCH_SIZE: Final[int] = 20
MAX_TOKENS_PER_BATCH: Final[int] = 3000
OPENAI_MODEL: Final[str] = "gpt-4o-mini"
RETRY_BACKOFF_SECONDS: Final[tuple[int, ...]] = (1, 4, 16)
TEST_REWRITE_SUFFIX: Final[str] = " [AI UNIQUE]"


@dataclass(frozen=True)
class RewriteNode:
    node_index: int
    tag: Tag
    original_html: str


def _copy_mutated_tree_sync(job_id: int) -> Path:
    job_dir = get_job_dir(job_id)
    mutated_dir = job_dir / "mutated"
    rewritten_dir = job_dir / "rewritten"

    if not mutated_dir.is_dir():
        raise FileNotFoundError(f"Mutated directory missing: {mutated_dir}")

    if rewritten_dir.exists():
        shutil.rmtree(rewritten_dir)
    shutil.copytree(mutated_dir, rewritten_dir)
    return rewritten_dir


def _extract_nodes_sync(html_file: Path) -> tuple[BeautifulSoup, list[RewriteNode]]:
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8", errors="replace"), "lxml")
    nodes: list[RewriteNode] = []

    for tag in soup.select(",".join(TEXT_NODES_SELECTOR)):
        if not isinstance(tag, Tag):
            continue
        visible_text = " ".join(tag.get_text(" ", strip=True).split())
        if len(visible_text) <= TEXT_NODE_MIN_LENGTH:
            continue
        nodes.append(
            RewriteNode(
                node_index=len(nodes),
                tag=tag,
                original_html="".join(str(child) for child in tag.contents),
            )
        )

    return soup, nodes


def _approx_token_count(text: str) -> int:
    return max(1, len(text) // 4)


def _build_batches(nodes: list[RewriteNode]) -> list[list[RewriteNode]]:
    batches: list[list[RewriteNode]] = []
    current: list[RewriteNode] = []
    current_tokens = 0

    for node in nodes:
        node_tokens = _approx_token_count(node.original_html)
        should_split = current and (
            len(current) >= BATCH_SIZE
            or current_tokens + node_tokens > MAX_TOKENS_PER_BATCH
        )
        if should_split:
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(node)
        current_tokens += node_tokens

    if current:
        batches.append(current)
    return batches


def _apply_test_rewrites(batches: list[list[RewriteNode]]) -> None:
    for batch in batches:
        for node in batch:
            fragment = BeautifulSoup(
                f"{node.original_html}{TEST_REWRITE_SUFFIX}",
                "html.parser",
            )
            node.tag.clear()
            for child in list(fragment.contents):
                node.tag.append(child)


def _rewrite_index_for_test_sync(job_id: int) -> Path:
    rewritten_dir = _copy_mutated_tree_sync(job_id)
    html_file = rewritten_dir / "index.html"
    soup, nodes = _extract_nodes_sync(html_file)
    _apply_test_rewrites(_build_batches(nodes))
    _write_soup_sync(html_file, soup)
    return rewritten_dir


def _write_soup_sync(html_file: Path, soup: BeautifulSoup) -> None:
    html_file.write_text(str(soup), encoding="utf-8")


async def module_ai_rewriter(job_id: int) -> None:
    await asyncio.to_thread(_rewrite_index_for_test_sync, job_id)
