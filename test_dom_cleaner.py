import tempfile
import unittest
from pathlib import Path

from backend import config, database
from backend.worker import dom_cleaner


class DomCleanerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.temp_path = Path(self.temp_dir.name)

        self.prev_jobs_workdir = config.JOBS_WORKDIR
        config.JOBS_WORKDIR = self.temp_path / "jobs"

        self.db_path = self.temp_path / "test.db"
        self.prev_database_url = database.DATABASE_URL
        database.DATABASE_URL = str(self.db_path)
        database.init_db()

    def tearDown(self) -> None:
        config.JOBS_WORKDIR = self.prev_jobs_workdir
        database.DATABASE_URL = self.prev_database_url
        self.temp_dir.cleanup()

    async def test_cleaner_clones_raw_to_cleaned_and_sanitizes_index_html(self) -> None:
        if dom_cleaner.BeautifulSoup is None:
            self.skipTest("beautifulsoup4 is not installed in this environment")

        job_id = 123
        raw_dir = config.get_job_dir(job_id) / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)

        (raw_dir / "assets").mkdir(parents=True, exist_ok=True)
        (raw_dir / "assets" / "a.txt").write_text("hello", encoding="utf-8")
        (raw_dir / "assets" / "sheet.css").write_text(
            'body{color:red}@import url("https://fonts.googleapis.com/css2?family=X");\np{color:blue}',
            encoding="utf-8",
        )

        raw_html = """
        <html><head>
          <meta http-equiv="Content-Security-Policy" content="default-src 'none'">
          <meta http-equiv="content-security-policy" content="img-src https:">
          <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Roboto">
          <script>alert(1)</script>
          <script src="https://www.googletagmanager.com/gtag/js?id=1"></script>
        </head>
        <body onload="x()">
          <!-- tracker noise -->
          <noscript>fallback</noscript>
          <iframe src="https://example.com/embed"></iframe>
          <iframe src="https://www.googletagmanager.com/ns.html?id=x"></iframe>
          <div onclick="y()" onmouseover="z()">hi <bdo>w</bdo><cite>c</cite></div>
        </body></html>
        """.strip()
        (raw_dir / "index.html").write_text(raw_html, encoding="utf-8")

        raw_before = (raw_dir / "index.html").read_text(encoding="utf-8")

        result = await dom_cleaner.clean_job_html(job_id, raw_dir, base_url="https://landing.example/")

        self.assertEqual((raw_dir / "index.html").read_text(encoding="utf-8"), raw_before)

        self.assertTrue((result.cleaned_dir / "assets" / "a.txt").exists())
        self.assertEqual(
            (result.cleaned_dir / "assets" / "a.txt").read_text(encoding="utf-8"),
            "hello",
        )

        cleaned_css = (result.cleaned_dir / "assets" / "sheet.css").read_text(encoding="utf-8")
        self.assertNotIn("fonts.googleapis.com", cleaned_css.lower())
        self.assertIn("color:red", cleaned_css)
        self.assertIn("color:blue", cleaned_css)

        cleaned_html = result.index_html_path.read_text(encoding="utf-8").lower()
        self.assertIn("<script", cleaned_html)
        self.assertIn("alert(1)", cleaned_html)
        self.assertNotIn("googletagmanager.com", cleaned_html)
        self.assertNotIn("<noscript", cleaned_html)
        self.assertIn("https://example.com/embed", cleaned_html)
        self.assertNotIn("googletagmanager.com/ns.html", cleaned_html.lower())
        self.assertNotIn("content-security-policy", cleaned_html)
        self.assertIn(" onload=", cleaned_html)
        self.assertIn(" onclick=", cleaned_html)
        self.assertIn(" onmouseover=", cleaned_html)
        self.assertNotIn("fonts.googleapis.com", cleaned_html)
        self.assertNotIn("tracker noise", cleaned_html)
        self.assertNotIn("<bdo", cleaned_html)
        self.assertNotIn("<cite", cleaned_html)
        # Проверяем, что текст остался, а теги <bdo>/<cite> исчезли
        self.assertIn("hi wc", cleaned_html)
        self.assertNotIn("<bdo>", cleaned_html)
        self.assertNotIn("<cite>", cleaned_html) # Тег cite удален

        self.assertEqual(
            result.google_font_css_urls,
            ("https://fonts.googleapis.com/css2?family=Roboto",),
        )

        stats = result.stats
        self.assertEqual(stats.removed_tracker_scripts, 1)
        self.assertEqual(stats.removed_tracker_iframes, 1)
        self.assertEqual(stats.removed_noscripts, 1)
        self.assertEqual(stats.removed_csp_meta, 2)
        self.assertEqual(stats.removed_html_comments, 1)
        self.assertEqual(stats.removed_google_font_links, 1)
        self.assertEqual(stats.removed_font_imports, 1)
        self.assertEqual(stats.removed_bdo_cite, 2)

    async def test_protocol_relative_tracker_script_resolved_and_removed(self) -> None:
        """//host/... inherits scheme from base_url; GTM script must match TRACKER_DOMAINS."""
        if dom_cleaner.BeautifulSoup is None:
            self.skipTest("beautifulsoup4 is not installed in this environment")

        job_id = 124
        raw_dir = config.get_job_dir(job_id) / "raw"
        raw_dir.mkdir(parents=True, exist_ok=True)
        raw_html = (
            "<html><head>"
            '<script src="//www.googletagmanager.com/gtag/js?id=1"></script>'
            "<script>keepInline();</script>"
            "</head><body></body></html>"
        )
        (raw_dir / "index.html").write_text(raw_html, encoding="utf-8")

        result = await dom_cleaner.clean_job_html(
            job_id, raw_dir, base_url="https://landing.example/page"
        )
        cleaned = result.index_html_path.read_text(encoding="utf-8").lower()
        self.assertIn("keepinline", cleaned)
        self.assertNotIn("googletagmanager.com", cleaned)
        self.assertEqual(result.stats.removed_tracker_scripts, 1)


if __name__ == "__main__":
    unittest.main()
