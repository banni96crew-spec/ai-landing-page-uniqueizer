"""Legacy SQLite files: ensure_db_schema adds jobs.updated_at (constant ADD default)."""

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

import backend.config as config
import backend.database as database


class LegacyJobsSchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self._prev_db = config.DATABASE_URL
        self._fd, self._path = tempfile.mkstemp(suffix=".db")
        os.close(self._fd)
        raw = sqlite3.connect(self._path)
        try:
            raw.executescript(
                """
                PRAGMA foreign_keys=OFF;
                CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_url TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    created_at TEXT NOT NULL DEFAULT ''
                );
                """
            )
            raw.commit()
        finally:
            raw.close()
        config.DATABASE_URL = self._path

    def tearDown(self) -> None:
        config.DATABASE_URL = self._prev_db
        database._SCHEMA_ENSURED_PATHS.discard(os.path.abspath(self._path))
        Path(self._path).unlink(missing_ok=True)

    def test_get_connection_adds_updated_at_and_allows_job_update(self) -> None:
        conn = database.get_connection()
        try:
            cols = database._table_column_names(conn, "jobs")
            self.assertIn("updated_at", cols)
            conn.execute(
                "INSERT INTO jobs (target_url, status) VALUES (?, ?)",
                ("https://example.com", "pending"),
            )
            conn.commit()
            row = conn.execute("SELECT id FROM jobs LIMIT 1").fetchone()
            assert row is not None
            job_id = int(row[0])
            conn.execute(
                "UPDATE jobs SET status = ? WHERE id = ?",
                ("running", job_id),
            )
            conn.commit()
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
