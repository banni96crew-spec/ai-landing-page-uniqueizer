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

        # Extra file proves we clone full tree.
        (raw_dir / "assets").mkdir(parents=True, exist_ok=True)
        (raw_dir / "assets" / "a.txt").write_text("hello", encoding="utf-8")

        raw_html = """
        <html><head>
          <meta http-equiv="Content-Security-Policy" content="default-src 'none'">
          <meta http-equiv="content-security-policy" content="img-src https:">
          <script>alert(1)</script>
        </head>
        <body onload="x()">
          <noscript>fallback</noscript>
          <iframe src="https://example.com"></iframe>
          <div onclick="y()" onmouseover="z()">hi</div>
        </body></html>
        """.strip()
        (raw_dir / "index.html").write_text(raw_html, encoding="utf-8")

        raw_before = (raw_dir / "index.html").read_text(encoding="utf-8")

        result = await dom_cleaner.clean_job_html(job_id, raw_dir)

        # raw untouched
        self.assertEqual((raw_dir / "index.html").read_text(encoding="utf-8"), raw_before)

        # cleaned created and self-contained clone
        self.assertTrue((result.cleaned_dir / "assets" / "a.txt").exists())
        self.assertEqual(
            (result.cleaned_dir / "assets" / "a.txt").read_text(encoding="utf-8"),
            "hello",
        )

        cleaned_html = result.index_html_path.read_text(encoding="utf-8")
        self.assertNotIn("<script", cleaned_html.lower())
        self.assertNotIn("<noscript", cleaned_html.lower())
        self.assertNotIn("<iframe", cleaned_html.lower())
        self.assertNotIn("content-security-policy", cleaned_html.lower())
        self.assertNotIn(" onload=", cleaned_html.lower())
        self.assertNotIn(" onclick=", cleaned_html.lower())
        self.assertNotIn(" onmouseover=", cleaned_html.lower())

        stats = result.stats
        self.assertEqual(stats.removed_scripts, 1)
        self.assertEqual(stats.removed_noscripts, 1)
        self.assertEqual(stats.removed_iframes, 1)
        self.assertEqual(stats.removed_csp_meta, 2)
        # 3 event handler attributes removed: onload, onclick, onmouseover
        self.assertEqual(stats.removed_inline_handlers, 3)


if __name__ == "__main__":
    unittest.main()

