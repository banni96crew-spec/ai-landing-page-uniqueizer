import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from backend import database
from backend.worker import module_scraper


class _FakePlaywrightContext:
    def __init__(self, playwright_api: object) -> None:
        self._playwright_api = playwright_api

    async def __aenter__(self) -> object:
        return self._playwright_api

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class ModuleScraperTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)
        self.db_path = self.temp_path / "test.db"
        self.previous_database_url = database.DATABASE_URL
        database.DATABASE_URL = str(self.db_path)
        database.init_db()

    def tearDown(self) -> None:
        database.DATABASE_URL = self.previous_database_url
        self.temp_dir.cleanup()

    def _insert_job(self, job_id: int) -> None:
        conn = database.get_connection()
        try:
            conn.execute(
                """
                INSERT INTO jobs (id, target_url, status, error_message)
                VALUES (?, ?, ?, NULL)
                """,
                (job_id, "https://example.com", "running"),
            )
            conn.commit()
        finally:
            conn.close()

    def _build_playwright_patch(
        self,
        *,
        html: str,
        page_url: str = "https://example.com",
        networkidle_side_effect: Exception | None = None,
        goto_side_effect: Exception | None = None,
    ) -> tuple[AsyncMock, AsyncMock, _FakePlaywrightContext]:
        page = AsyncMock()
        page.url = page_url
        page.content.return_value = html
        page.wait_for_load_state.side_effect = networkidle_side_effect
        page.goto.side_effect = goto_side_effect

        context = AsyncMock()
        context.new_page.return_value = page

        browser = AsyncMock()
        browser.new_context.return_value = context

        playwright_api = SimpleNamespace(
            chromium=SimpleNamespace(launch=AsyncMock(return_value=browser))
        )
        return page, browser, _FakePlaywrightContext(playwright_api)

    def _get_logs(self, job_id: int) -> list[tuple[str, str]]:
        conn = database.get_connection()
        try:
            rows = conn.execute(
                "SELECT level, message FROM logs WHERE job_id = ? ORDER BY id ASC",
                (job_id,),
            ).fetchall()
            return [(str(row["level"]), str(row["message"])) for row in rows]
        finally:
            conn.close()

    async def test_scrape_saves_html_and_returns_raw_dir(self) -> None:
        page, browser, playwright_context = self._build_playwright_patch(
            html="<html>" + ("a" * 1200) + "</html>"
        )
        raw_root = self.temp_path / "jobs" / "1"

        with (
            patch.object(module_scraper, "async_playwright", return_value=playwright_context),
            patch.object(module_scraper, "get_job_dir", return_value=raw_root),
        ):
            raw_dir = await module_scraper.scrape(1, "https://example.com")

        self.assertEqual(raw_dir, raw_root / "raw")
        self.assertTrue((raw_dir / "index.html").exists())
        self.assertIn("a" * 1200, (raw_dir / "index.html").read_text(encoding="utf-8"))
        page.goto.assert_awaited_once_with(
            "https://example.com",
            wait_until="domcontentloaded",
            timeout=module_scraper.SCRAPER_PAGE_TIMEOUT_SECONDS * 1000,
        )
        page.wait_for_load_state.assert_awaited_once_with(
            "networkidle",
            timeout=module_scraper.NETWORKIDLE_TIMEOUT_MS,
        )
        page.evaluate.assert_awaited_once_with(
            "window.scrollTo(0, document.body.scrollHeight)"
        )
        page.wait_for_timeout.assert_awaited_once_with(
            module_scraper.LAZY_LOAD_WAIT_MS
        )
        browser.close.assert_awaited_once()

    async def test_scrape_rewrites_assets_before_writing_raw_html(self) -> None:
        original_html = "<html>" + ("r" * 1200) + "</html>"
        rewritten_html = "<html>" + ("w" * 1200) + "</html>"
        _, _, playwright_context = self._build_playwright_patch(html=original_html)
        raw_root = self.temp_path / "jobs" / "7"

        with (
            patch.object(module_scraper, "async_playwright", return_value=playwright_context),
            patch.object(module_scraper, "get_job_dir", return_value=raw_root),
            patch.object(
                module_scraper,
                "_rewrite_scraped_assets",
                new=AsyncMock(return_value=rewritten_html),
            ) as rewrite_mock,
        ):
            raw_dir = await module_scraper.scrape(7, "https://example.com")

        rewrite_mock.assert_awaited_once_with(
            job_id=7,
            target_url="https://example.com",
            raw_dir=raw_root / "raw",
            html=original_html,
        )
        self.assertEqual(
            (raw_dir / "index.html").read_text(encoding="utf-8"),
            rewritten_html,
        )

    async def test_scrape_logs_warn_and_continues_on_networkidle_timeout(self) -> None:
        self._insert_job(2)
        page, _, playwright_context = self._build_playwright_patch(
            html="<html>" + ("b" * 1300) + "</html>",
            networkidle_side_effect=module_scraper.PlaywrightTimeoutError("slow network"),
        )
        raw_root = self.temp_path / "jobs" / "2"

        with (
            patch.object(module_scraper, "async_playwright", return_value=playwright_context),
            patch.object(module_scraper, "get_job_dir", return_value=raw_root),
        ):
            raw_dir = await module_scraper.scrape(2, "https://example.com")

        self.assertEqual(raw_dir, raw_root / "raw")
        self.assertEqual(
            self._get_logs(2),
            [("warn", "networkidle timeout, using partial DOM")],
        )
        page.content.assert_awaited_once()

    async def test_scrape_raises_on_navigation_timeout(self) -> None:
        _, browser, playwright_context = self._build_playwright_patch(
            html="<html>" + ("d" * 1300) + "</html>",
            goto_side_effect=module_scraper.PlaywrightTimeoutError("timeout"),
        )

        with (
            patch.object(module_scraper, "async_playwright", return_value=playwright_context),
            patch.object(
                module_scraper,
                "get_job_dir",
                return_value=self.temp_path / "jobs" / "6",
            ),
        ):
            with self.assertRaisesRegex(
                module_scraper.ScraperError,
                "Target URL unreachable or timeout",
            ):
                await module_scraper.scrape(6, "https://example.com")

        browser.close.assert_awaited_once()

    async def test_scrape_raises_on_antibot_redirect(self) -> None:
        _, _, playwright_context = self._build_playwright_patch(
            html="<html>" + ("c" * 1300) + "</html>",
            page_url="https://example.com/captcha",
        )

        with (
            patch.object(module_scraper, "async_playwright", return_value=playwright_context),
            patch.object(
                module_scraper,
                "get_job_dir",
                return_value=self.temp_path / "jobs" / "3",
            ),
        ):
            with self.assertRaisesRegex(
                module_scraper.ScraperError,
                "Target URL blocked by anti-bot",
            ):
                await module_scraper.scrape(3, "https://example.com")

    async def test_scrape_raises_on_small_html(self) -> None:
        _, _, playwright_context = self._build_playwright_patch(
            html="<html>tiny</html>"
        )

        with (
            patch.object(module_scraper, "async_playwright", return_value=playwright_context),
            patch.object(
                module_scraper,
                "get_job_dir",
                return_value=self.temp_path / "jobs" / "4",
            ),
        ):
            with self.assertRaisesRegex(
                module_scraper.ScraperError,
                "Scraped HTML too small, possible bot detection",
            ):
                await module_scraper.scrape(4, "https://example.com")

    async def test_module_scraper_discards_path_result(self) -> None:
        with patch.object(
            module_scraper,
            "scrape",
            new=AsyncMock(return_value=self.temp_path / "jobs" / "5" / "raw"),
        ) as scrape_mock:
            result = await module_scraper.module_scraper(5, "https://example.com")

        self.assertIsNone(result)
        scrape_mock.assert_awaited_once_with(5, "https://example.com")


if __name__ == "__main__":
    unittest.main()
