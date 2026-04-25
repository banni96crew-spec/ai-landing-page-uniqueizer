import asyncio
import tempfile
import unittest
from pathlib import Path

from backend import config
from backend.worker.module_ai_rewriter import TEST_REWRITE_SUFFIX, module_ai_rewriter


class AiRewriterTestStubTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.previous_jobs_workdir = config.JOBS_WORKDIR
        config.JOBS_WORKDIR = self.root / "jobs"

    def tearDown(self) -> None:
        config.JOBS_WORKDIR = self.previous_jobs_workdir
        self.temp_dir.cleanup()

    def test_copies_mutated_tree_and_appends_suffix_to_text_nodes(self) -> None:
        job_id = 1
        mutated_dir = config.get_job_dir(job_id) / "mutated"
        assets_dir = mutated_dir / "assets"
        assets_dir.mkdir(parents=True)
        (assets_dir / "style.css").write_text(".hero { color: red; }", encoding="utf-8")
        (mutated_dir / "index.html").write_text(
            "<html><body>"
            "<h1>Winning headline text</h1>"
            "<p>Paragraph with <b>bold value</b> included.</p>"
            "<span>Short</span>"
            "<a>Anchor text should not change</a>"
            "</body></html>",
            encoding="utf-8",
        )

        asyncio.run(module_ai_rewriter(job_id))

        rewritten_dir = config.get_job_dir(job_id) / "rewritten"
        mutated_html = (mutated_dir / "index.html").read_text(encoding="utf-8")
        rewritten_html = (rewritten_dir / "index.html").read_text(encoding="utf-8")

        self.assertTrue((rewritten_dir / "assets" / "style.css").exists())
        self.assertIn(f"Winning headline text{TEST_REWRITE_SUFFIX}", rewritten_html)
        self.assertIn(f"<b>bold value</b> included.{TEST_REWRITE_SUFFIX}", rewritten_html)
        self.assertIn("<span>Short</span>", rewritten_html)
        self.assertIn("<a>Anchor text should not change</a>", rewritten_html)
        self.assertNotIn(TEST_REWRITE_SUFFIX, mutated_html)


if __name__ == "__main__":
    unittest.main()
