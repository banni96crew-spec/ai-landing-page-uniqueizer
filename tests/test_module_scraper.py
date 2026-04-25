import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

from backend import config, database
from backend.worker.asset_rewriter import AssetRewriteResult
from backend.worker import dom_cleaner, module_scraper
from backend.worker.dom_cleaner import DomCleanResult, DomCleanStats


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
        self.previous_database_url = config.DATABASE_URL
        config.DATABASE_URL = str(self.db_path)
        database.init_db()

    def tearDown(self) -> None:
        config.DATABASE_URL = self.previous_database_url
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
        rewrite_result = AssetRewriteResult(html=rewritten_html, css_file_origins={})

        with (
            patch.object(module_scraper, "async_playwright", return_value=playwright_context),
            patch.object(module_scraper, "get_job_dir", return_value=raw_root),
            patch.object(
                module_scraper,
                "_rewrite_scraped_assets",
                new=AsyncMock(return_value=rewrite_result),
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
        dummy_result = DomCleanResult(
            cleaned_dir=self.temp_path / "jobs" / "5" / "cleaned",
            index_html_path=self.temp_path / "jobs" / "5" / "cleaned" / "index.html",
            stats=DomCleanStats(
                removed_tracker_scripts=1,
                removed_tracker_iframes=2,
                removed_noscripts=3,
                removed_csp_meta=4,
                removed_html_comments=0,
                removed_google_font_links=0,
                removed_font_imports=0,
                removed_bdo_cite=0,
            ),
        )
        self._insert_job(5)
        with patch.object(
            module_scraper,
            "scrape",
            new=AsyncMock(return_value=self.temp_path / "jobs" / "5" / "raw"),
        ) as scrape_mock, patch.object(
            module_scraper,
            "clean",
            new=AsyncMock(return_value=dummy_result.cleaned_dir),
        ) as cleaner_mock:
            result = await module_scraper.module_scraper(5, "https://example.com")

        self.assertIsNone(result)
        scrape_mock.assert_awaited_once_with(5, "https://example.com")
        cleaner_mock.assert_awaited_once_with(
            self.temp_path / "jobs" / "5" / "raw", 5, base_url="https://example.com"
        )

    async def test_clean_creates_cleaned_dir_and_logs_dom_cleaner_stats(self) -> None:
        if dom_cleaner.BeautifulSoup is None:
            self.skipTest("beautifulsoup4 is not installed in this environment")

        prev_jobs_workdir = config.JOBS_WORKDIR
        config.JOBS_WORKDIR = self.temp_path / "jobs_clean_test"
        try:
            job_id = 99
            self._insert_job(job_id)
            raw_dir = config.get_job_dir(job_id) / "raw"
            raw_dir.mkdir(parents=True, exist_ok=True)
            (raw_dir / "index.html").write_text(
                "<html><head>"
                '<script src="https://www.googletagmanager.com/gtag/js?id=1"></script>'
                '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=X">'
                "</head><body><!--x--><noscript>n</noscript></body></html>",
                encoding="utf-8",
            )

            cleaned_dir = await module_scraper.clean(
                raw_dir, job_id, base_url="https://example.com/landing"
            )

            self.assertEqual(cleaned_dir, config.get_job_dir(job_id) / "cleaned")
            idx = (cleaned_dir / "index.html").read_text(encoding="utf-8").lower()
            self.assertNotIn("googletagmanager.com", idx)
            self.assertNotIn("fonts.googleapis.com", idx)
            self.assertNotIn("<noscript", idx)
            self.assertNotIn("<!--x-->", idx)
            self.assertEqual((raw_dir / "index.html").read_text(encoding="utf-8").count("googletagmanager"), 1)

            messages = [m for _, m in self._get_logs(job_id)]
            self.assertTrue(
                any(m.startswith("dom_cleaner: removed tracker scripts: 1") for m in messages)
            )
            self.assertTrue(
                any(m.startswith("dom_cleaner: removed Google Fonts link tags: 1") for m in messages)
            )
            self.assertTrue(
                any(m.startswith("dom_cleaner: removed noscript tags: 1") for m in messages)
            )
            self.assertTrue(
                any(m.startswith("dom_cleaner: removed HTML comments: 1") for m in messages)
            )
        finally:
            config.JOBS_WORKDIR = prev_jobs_workdir


class _FakeStreamResponse:
    def __init__(self, *, status_code: int, body: bytes, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    async def aiter_bytes(self, *, chunk_size: int = 65536):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]


class _FakeStreamContext:
    def __init__(self, response: _FakeStreamResponse):
        self._response = response

    async def __aenter__(self) -> _FakeStreamResponse:
        return self._response

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


class _FakeHttpxClient:
    def __init__(self, routes: dict[str, _FakeStreamResponse | Exception]):
        self._routes = routes
        self.stream_calls: list[str] = []

    def stream(self, method: str, url: str):
        self.stream_calls.append(f"{method} {url}")
        response = self._routes.get(url) or _FakeStreamResponse(status_code=404, body=b"")
        if isinstance(response, Exception):
            raise response
        return _FakeStreamContext(response)


class AssetRewriteTests(unittest.IsolatedAsyncioTestCase):
    def _patch_httpx_client(self, client: _FakeHttpxClient):
        httpx_patcher = patch.object(module_scraper, "httpx")
        httpx_mod = httpx_patcher.start()
        self.addCleanup(httpx_patcher.stop)
        httpx_mod.Timeout.return_value = None
        httpx_mod.AsyncClient.return_value.__aenter__ = AsyncMock(return_value=client)
        httpx_mod.AsyncClient.return_value.__aexit__ = AsyncMock(return_value=None)
        return httpx_mod

    async def test_rewrite_scraped_assets_downloads_and_rewrites_src_href_and_srcset(self) -> None:
        job_id = 11
        raw_dir = self._make_temp_raw_dir()
        html = (
            "<html><head>"
            '<link rel="stylesheet" href="//cdn.example.com/site.css">'
            "</head><body>"
            '<img src="/img/logo.png" srcset="/img/a.png 1x, /img/b.png 2x">'
            '<a href="data:text/plain,hello">skip</a>'
            "</body></html>"
        )

        base_url = "https://example.com/path/"
        base_scheme = urlparse(base_url).scheme

        routes = {
            "https://cdn.example.com/site.css": _FakeStreamResponse(
                status_code=200, body=b"body{color:red}"
            ),
            "https://example.com/img/logo.png": _FakeStreamResponse(
                status_code=200, body=b"PNGDATA"
            ),
            "https://example.com/img/a.png": _FakeStreamResponse(status_code=200, body=b"A"),
            "https://example.com/img/b.png": _FakeStreamResponse(status_code=200, body=b"BB"),
        }
        client = _FakeHttpxClient(routes)

        with self._patch_httpx_client(client):
            rewrite_result = await module_scraper._rewrite_scraped_assets(
                job_id=job_id, target_url=base_url, raw_dir=raw_dir, html=html
            )
        rewritten = rewrite_result.html

        # href rewritten to local file under ./assets/
        self.assertIn('href="./assets/site.css"', rewritten)
        # src rewritten
        self.assertIn('src="./assets/logo.png"', rewritten)
        # srcset rewritten but preserves descriptors
        self.assertIn('srcset="./assets/a.png 1x, ./assets/b.png 2x"', rewritten)
        # data: URLs remain unchanged
        self.assertIn('href="data:text/plain,hello"', rewritten)

        assets_dir = raw_dir / "assets"
        self.assertTrue((assets_dir / "site.css").exists())
        self.assertTrue((assets_dir / "logo.png").exists())
        self.assertTrue((assets_dir / "a.png").exists())
        self.assertTrue((assets_dir / "b.png").exists())

        # Ensure scheme inheritance for //... used base scheme.
        self.assertIn(f"GET {base_scheme}://cdn.example.com/site.css", client.stream_calls)

    async def test_rewrite_scraped_assets_uses_cache_for_duplicate_urls(self) -> None:
        raw_dir = self._make_temp_raw_dir()
        html = (
            "<html><body>"
            '<img src="/img/logo.png">'
            '<img src="/img/logo.png">'
            "</body></html>"
        )
        routes = {
            "https://example.com/img/logo.png": _FakeStreamResponse(status_code=200, body=b"X")
        }
        client = _FakeHttpxClient(routes)

        with self._patch_httpx_client(client):
            await module_scraper._rewrite_scraped_assets(
                job_id=1, target_url="https://example.com", raw_dir=raw_dir, html=html
            )

        self.assertEqual(client.stream_calls.count("GET https://example.com/img/logo.png"), 1)

    async def test_rewrite_scraped_assets_falls_back_on_asset_too_large(self) -> None:
        raw_dir = self._make_temp_raw_dir()
        html = "<html><body><img src='/big.bin'></body></html>"
        routes = {
            "https://example.com/big.bin": _FakeStreamResponse(
                status_code=200,
                body=b"0123456789",
                headers={"content-length": "10"},
            )
        }
        client = _FakeHttpxClient(routes)

        from backend.worker import asset_rewriter

        with patch.object(asset_rewriter, "ASSET_MAX_SIZE_BYTES", 5), self._patch_httpx_client(
            client
        ):
            rewrite_result = await module_scraper._rewrite_scraped_assets(
                job_id=1, target_url="https://example.com", raw_dir=raw_dir, html=html
            )
        rewritten = rewrite_result.html

        # Too large => keep original URL
        self.assertTrue(("src=\"/big.bin\"" in rewritten) or ("src='/big.bin'" in rewritten))
        self.assertFalse((raw_dir / "assets" / "big.bin").exists())

    async def test_rewrite_scraped_assets_skips_non_http_schemes(self) -> None:
        raw_dir = self._make_temp_raw_dir()
        html = (
            "<html><body>"
            '<img src="data:image/png;base64,abc">'
            '<a href="javascript:void(0)">click</a>'
            '<a href="mailto:test@example.com">mail</a>'
            '<a href="tel:+123456">phone</a>'
            '<form action="#signup"></form>'
            "</body></html>"
        )
        client = _FakeHttpxClient({})

        with self._patch_httpx_client(client):
            rewrite_result = await module_scraper._rewrite_scraped_assets(
                job_id=3, target_url="https://example.com", raw_dir=raw_dir, html=html
            )
        rewritten = rewrite_result.html

        self.assertIn('src="data:image/png;base64,abc"', rewritten)
        self.assertIn('href="javascript:void(0)"', rewritten)
        self.assertIn('href="mailto:test@example.com"', rewritten)
        self.assertIn('href="tel:+123456"', rewritten)
        self.assertIn('action="#signup"', rewritten)
        self.assertEqual(client.stream_calls, [])

    async def test_rewrite_scraped_assets_skips_external_non_assets_and_denied_hosts(
        self,
    ) -> None:
        raw_dir = self._make_temp_raw_dir()
        html = (
            "<html><body>"
            '<a href="https://www.sec.gov/Archives/report">SEC filing</a>'
            '<a href="https://patreon.com/creator">Patreon</a>'
            '<a href="https://linkedin.com/company/example">LinkedIn</a>'
            '<a href="https://external.example.org/privacy">Privacy</a>'
            '<img src="https://external.example.org/photo.png">'
            '<img src="https://example.com/img/logo.png">'
            '<script src="https://cdn.jsdelivr.net/npm/pkg/app.js"></script>'
            "</body></html>"
        )
        client = _FakeHttpxClient(
            {
                "https://example.com/img/logo.png": _FakeStreamResponse(
                    status_code=200,
                    body=b"LOGO",
                ),
                "https://cdn.jsdelivr.net/npm/pkg/app.js": _FakeStreamResponse(
                    status_code=200,
                    body=b"console.log(1)",
                ),
            }
        )

        with self._patch_httpx_client(client):
            rewrite_result = await module_scraper._rewrite_scraped_assets(
                job_id=8,
                target_url="https://example.com/landing",
                raw_dir=raw_dir,
                html=html,
            )
        rewritten = rewrite_result.html

        self.assertIn('href="https://www.sec.gov/Archives/report"', rewritten)
        self.assertIn('href="https://patreon.com/creator"', rewritten)
        self.assertIn('href="https://linkedin.com/company/example"', rewritten)
        self.assertIn('href="https://external.example.org/privacy"', rewritten)
        self.assertIn('src="https://external.example.org/photo.png"', rewritten)
        self.assertIn('src="./assets/logo.png"', rewritten)
        self.assertIn('src="./assets/app.js"', rewritten)
        self.assertEqual(
            client.stream_calls,
            [
                "GET https://example.com/img/logo.png",
                "GET https://cdn.jsdelivr.net/npm/pkg/app.js",
            ],
        )

    async def test_rewrite_scraped_assets_keeps_original_url_on_http_error_and_exception(
        self,
    ) -> None:
        raw_dir = self._make_temp_raw_dir()
        html = (
            "<html><body>"
            '<img src="/missing.png">'
            '<div data-src="/boom.png"></div>'
            '<img srcset="/ok.png 1x, /broken.png 2x">'
            "</body></html>"
        )
        client = _FakeHttpxClient(
            {
                "https://example.com/missing.png": _FakeStreamResponse(
                    status_code=404,
                    body=b"",
                ),
                "https://example.com/boom.png": RuntimeError("socket closed"),
                "https://example.com/ok.png": _FakeStreamResponse(status_code=200, body=b"OK"),
                "https://example.com/broken.png": RuntimeError("network failed"),
            }
        )

        with self._patch_httpx_client(client):
            rewrite_result = await module_scraper._rewrite_scraped_assets(
                job_id=4, target_url="https://example.com", raw_dir=raw_dir, html=html
            )
        rewritten = rewrite_result.html

        self.assertIn('src="/missing.png"', rewritten)
        self.assertIn('data-src="/boom.png"', rewritten)
        self.assertIn('srcset="./assets/ok.png 1x, /broken.png 2x"', rewritten)
        self.assertFalse((raw_dir / "assets" / "missing.png").exists())
        self.assertFalse((raw_dir / "assets" / "boom.png").exists())
        self.assertFalse((raw_dir / "assets" / "broken.png").exists())
        self.assertTrue((raw_dir / "assets" / "ok.png").exists())

    async def test_rewrite_scraped_assets_suffixes_colliding_filenames(self) -> None:
        raw_dir = self._make_temp_raw_dir()
        html = (
            "<html><body>"
            '<img src="https://cdn.example.com/shared/logo.png">'
            '<img src="https://assets.example.com/brand/logo.png">'
            "</body></html>"
        )
        client = _FakeHttpxClient(
            {
                "https://cdn.example.com/shared/logo.png": _FakeStreamResponse(
                    status_code=200,
                    body=b"FIRST",
                ),
                "https://assets.example.com/brand/logo.png": _FakeStreamResponse(
                    status_code=200,
                    body=b"SECOND",
                ),
            }
        )

        with self._patch_httpx_client(client):
            rewrite_result = await module_scraper._rewrite_scraped_assets(
                job_id=5, target_url="https://example.com", raw_dir=raw_dir, html=html
            )
        rewritten = rewrite_result.html

        self.assertIn('src="./assets/logo.png"', rewritten)
        self.assertIn('src="./assets/logo_1.png"', rewritten)
        self.assertTrue((raw_dir / "assets" / "logo.png").exists())
        self.assertTrue((raw_dir / "assets" / "logo_1.png").exists())

    async def test_rewrite_scraped_assets_rewrites_css_urls_against_css_origin(self) -> None:
        raw_dir = self._make_temp_raw_dir()
        html = (
            "<html><head>"
            '<link rel="stylesheet" href="//cdn.example.com/css/site.css">'
            "</head><body></body></html>"
        )
        client = _FakeHttpxClient(
            {
                "https://cdn.example.com/css/site.css": _FakeStreamResponse(
                    status_code=200,
                    body=(
                        b"@font-face{src:url('../fonts/font.woff2')}"
                        b".hero{background:url(\"data:image/png;base64,abc\")}"
                    ),
                ),
                "https://cdn.example.com/fonts/font.woff2": _FakeStreamResponse(
                    status_code=200,
                    body=b"FONTDATA",
                ),
            }
        )

        with self._patch_httpx_client(client):
            rewrite_result = await module_scraper._rewrite_scraped_assets(
                job_id=6,
                target_url="https://example.com/landing/index.html",
                raw_dir=raw_dir,
                html=html,
            )

        self.assertEqual(
            rewrite_result.css_file_origins,
            {"assets/site.css": "https://cdn.example.com/css/site.css"},
        )
        css_text = (raw_dir / "assets" / "site.css").read_text(encoding="utf-8")
        self.assertIn("url('font.woff2')", css_text)
        self.assertIn('url("data:image/png;base64,abc")', css_text)
        self.assertTrue((raw_dir / "assets" / "font.woff2").exists())
        self.assertIn("GET https://cdn.example.com/fonts/font.woff2", client.stream_calls)

    def _make_temp_raw_dir(self) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        raw_dir = Path(temp_dir.name) / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        return raw_dir


if __name__ == "__main__":
    unittest.main()
