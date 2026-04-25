import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backend import config, database
from backend.worker.module_dom_mutator import build_selector_map


class DomMutatorSelectorMapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.previous_database_url = config.DATABASE_URL
        config.DATABASE_URL = str(self.db_path)
        database.init_db()

    def tearDown(self) -> None:
        config.DATABASE_URL = self.previous_database_url
        self.temp_dir.cleanup()

    def _set_prefixes(self, csv_value: str) -> None:
        conn = database.get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                ("js_class_exclusion_prefixes", csv_value),
            )
            conn.commit()
        finally:
            conn.close()

    def test_extracts_and_filters_by_prefix_case_insensitive(self) -> None:
        self._set_prefixes("js-,SWIPER-")
        css = """
        .order-btn{color:red}
        #hero { display:block }
        .js-track { opacity:0 }
        .Swiper-slide{ transform: translateX(0) }
        """
        css_path = Path(self.temp_dir.name) / "a.css"
        css_path.write_text(css, encoding="utf-8")

        selector_map = build_selector_map([css_path])

        self.assertIn(".order-btn", selector_map)
        self.assertIn("#hero", selector_map)
        self.assertNotIn(".js-track", selector_map)
        self.assertNotIn(".Swiper-slide", selector_map)

        self.assertTrue(selector_map[".order-btn"].startswith(".x"))
        self.assertTrue(selector_map["#hero"].startswith("#x"))
        self.assertEqual(len(selector_map[".order-btn"]), 6)  # ".x" + 4 hex
        self.assertEqual(len(selector_map["#hero"]), 6)  # "#x" + 4 hex

    def test_is_deterministic_for_same_inputs(self) -> None:
        self._set_prefixes("js-")
        css_path = Path(self.temp_dir.name) / "b.css"
        css_path.write_text(".a{c:1} #b{c:2} .c:hover{c:3}", encoding="utf-8")

        first = build_selector_map([css_path])
        second = build_selector_map([css_path])

        self.assertEqual(first, second)

    def test_collision_resolution_is_unique(self) -> None:
        self._set_prefixes("")
        css_path = Path(self.temp_dir.name) / "c.css"
        css_path.write_text(".a{c:1}.b{c:2}", encoding="utf-8")

        class _FakeMd5:
            def __init__(self, payload: bytes):
                self._payload = payload

            def hexdigest(self) -> str:
                # Force collisions by returning same first 4 hex
                # unless salt is 1 (payload ends with b'|1').
                if self._payload.endswith(b"|1"):
                    return "bbbb" + "0" * 28
                return "aaaa" + "0" * 28

        def _fake_md5(payload: bytes):
            return _FakeMd5(payload)

        with patch.object(hashlib, "md5", side_effect=_fake_md5):
            selector_map = build_selector_map([css_path])

        self.assertEqual(selector_map[".a"], ".xaaaa")
        self.assertEqual(selector_map[".b"], ".xbbbb")
        self.assertNotEqual(selector_map[".a"], selector_map[".b"])


if __name__ == "__main__":
    unittest.main()

