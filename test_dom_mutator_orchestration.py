import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import config, database
from backend.worker import module_dom_mutator


class DomMutatorOrchestrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.db_path = self.root / "test.db"
        self.previous_database_url = database.DATABASE_URL
        self.previous_jobs_workdir = config.JOBS_WORKDIR
        database.DATABASE_URL = str(self.db_path)
        config.JOBS_WORKDIR = self.root / "jobs"
        database.init_db()

    def tearDown(self) -> None:
        database.DATABASE_URL = self.previous_database_url
        config.JOBS_WORKDIR = self.previous_jobs_workdir
        self.temp_dir.cleanup()

    def test_copies_cleaned_tree_and_mutates_outputs_only(self) -> None:
        job_id = 1
        cleaned_dir = config.get_job_dir(job_id) / "cleaned"
        assets_dir = cleaned_dir / "assets"
        assets_dir.mkdir(parents=True)
        (cleaned_dir / "index.html").write_text(
            '<html><head></head><body><section id="hero" class="btn untouched">'
            "Buy</section></body></html>",
            encoding="utf-8",
        )
        (assets_dir / "style.css").write_text(
            ".btn { color: red; } #hero { display: block; }",
            encoding="utf-8",
        )
        (assets_dir / "app.js").write_text(
            "document.querySelector('.btn'); document.getElementById('hero');",
            encoding="utf-8",
        )

        selector_map = {".btn": ".x1111", "#hero": "#x2222"}
        with patch.object(module_dom_mutator, "build_selector_map", return_value=selector_map):
            mutated_dir = module_dom_mutator.mutate_cleaned_tree(job_id)

        cleaned_html = (cleaned_dir / "index.html").read_text(encoding="utf-8")
        mutated_html = (mutated_dir / "index.html").read_text(encoding="utf-8")
        mutated_css = (mutated_dir / "assets" / "style.css").read_text(encoding="utf-8")
        mutated_js = (mutated_dir / "assets" / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="hero" class="btn untouched"', cleaned_html)
        self.assertIn('id="x2222"', mutated_html)
        self.assertIn("x1111", mutated_html)
        self.assertIn("untouched", mutated_html)
        self.assertIn("display: none; opacity: 0;", mutated_html)
        self.assertIn(".x1111 { color: red; }", mutated_css)
        self.assertIn("#x2222 { display: block; }", mutated_css)
        self.assertIn("document.querySelector('.x1111');", mutated_js)
        self.assertIn("document.getElementById('x2222');", mutated_js)

    def test_randomizes_inter_tag_whitespace_from_allowed_choices(self) -> None:
        html = "<main> <section>Content</section> <footer>End</footer></main>"

        with patch.object(
            module_dom_mutator.random,
            "choice",
            side_effect=[" ", "\n  "],
        ):
            mutated = module_dom_mutator._randomize_inter_tag_whitespace(html)

        self.assertIn("> <", mutated)
        self.assertIn(">\n  <", mutated)
        self.assertIn("<section>Content</section>", mutated)

    def test_noise_aliases_are_random_and_avoid_selector_aliases(self) -> None:
        selector_map = {".btn": ".x1111"}

        with patch.object(
            module_dom_mutator.random,
            "randint",
            side_effect=[0x1111, 0x2222, 0x3333, 0x4444],
        ):
            aliases = module_dom_mutator._noise_aliases(selector_map)

        self.assertEqual(["x2222", "x3333", "x4444"], aliases)
        self.assertNotIn("x1111", aliases)
        self.assertEqual(len(aliases), len(set(aliases)))


if __name__ == "__main__":
    unittest.main()
