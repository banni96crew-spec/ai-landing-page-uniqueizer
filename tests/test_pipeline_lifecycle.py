import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from backend import config, database
from backend.job_progress import calculate_progress_pct
from backend.state import JOB_QUEUES
from backend.worker import pipeline


class PipelineLifecycleTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.previous_database_url = config.DATABASE_URL
        config.DATABASE_URL = str(self.db_path)
        JOB_QUEUES.clear()
        database.init_db()

    def tearDown(self) -> None:
        JOB_QUEUES.clear()
        config.DATABASE_URL = self.previous_database_url
        self.temp_dir.cleanup()

    def _create_job(self, status: str = "running") -> int:
        conn = database.get_connection()
        try:
            cursor = conn.execute(
                """
                INSERT INTO jobs (target_url, status, error_message)
                VALUES (?, ?, NULL)
                """,
                ("https://example.com", status),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def _get_job_row(self, job_id: int) -> dict[str, object]:
        conn = database.get_connection()
        try:
            row = conn.execute(
                "SELECT id, status, error_message FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            return dict(row)
        finally:
            conn.close()

    def _get_log_messages(self, job_id: int) -> list[str]:
        conn = database.get_connection()
        try:
            rows = conn.execute(
                "SELECT message FROM logs WHERE job_id = ? ORDER BY id ASC",
                (job_id,),
            ).fetchall()
            return [str(row["message"]) for row in rows]
        finally:
            conn.close()

    async def test_run_pipeline_marks_done_and_logs_all_markers(self) -> None:
        job_id = self._create_job()

        with (
            patch.object(pipeline, "module_scraper", new=AsyncMock()),
            patch.object(pipeline, "module_dom_mutator", new=AsyncMock()),
            patch.object(pipeline, "module_ai_rewriter", new=AsyncMock()),
            patch.object(pipeline, "module_media_uniqueizer", new=AsyncMock()),
            patch.object(pipeline, "module_packer", new=AsyncMock()),
        ):
            await pipeline.run_pipeline(job_id, "https://example.com")

        job = self._get_job_row(job_id)
        messages = self._get_log_messages(job_id)

        self.assertEqual(job["status"], "done")
        self.assertIsNone(job["error_message"])
        self.assertEqual(
            messages,
            [
                "MODULE_SCRAPER_DONE",
                "MODULE_DOM_MUTATOR_DONE",
                "MODULE_AI_REWRITER_DONE",
                "MODULE_MEDIA_UNIQUEIZER_DONE",
                "MODULE_PACKER_DONE",
            ],
        )

    async def test_run_pipeline_marks_failed_and_stops_after_exception(self) -> None:
        job_id = self._create_job()
        dom_error = RuntimeError("dom exploded")
        scraper_mock = AsyncMock()
        dom_mock = AsyncMock(side_effect=dom_error)
        rewriter_mock = AsyncMock()

        with (
            patch.object(pipeline, "module_scraper", new=scraper_mock),
            patch.object(pipeline, "module_dom_mutator", new=dom_mock),
            patch.object(pipeline, "module_ai_rewriter", new=rewriter_mock),
            patch.object(pipeline, "module_media_uniqueizer", new=AsyncMock()),
            patch.object(pipeline, "module_packer", new=AsyncMock()),
        ):
            with self.assertRaises(RuntimeError):
                await pipeline.run_pipeline(job_id, "https://example.com")

        job = self._get_job_row(job_id)
        messages = self._get_log_messages(job_id)

        self.assertEqual(job["status"], "failed")
        self.assertEqual(job["error_message"], "dom exploded")
        self.assertEqual(messages, ["MODULE_SCRAPER_DONE", "dom exploded"])
        self.assertEqual(rewriter_mock.await_count, 0)


class JobProgressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.previous_database_url = config.DATABASE_URL
        config.DATABASE_URL = str(self.db_path)
        JOB_QUEUES.clear()
        database.init_db()

    def tearDown(self) -> None:
        JOB_QUEUES.clear()
        config.DATABASE_URL = self.previous_database_url
        self.temp_dir.cleanup()

    def _create_job_with_logs(self, status: str, messages: list[str]) -> int:
        conn = database.get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO jobs (target_url, status) VALUES (?, ?)",
                ("https://example.com", status),
            )
            job_id = int(cursor.lastrowid)
            for message in messages:
                conn.execute(
                    "INSERT INTO logs (job_id, level, message) VALUES (?, ?, ?)",
                    (job_id, "info", message),
                )
            conn.commit()
            return job_id
        finally:
            conn.close()

    def _get_progress_pct(self, job_id: int) -> int:
        conn = database.get_connection()
        try:
            row = conn.execute(
                "SELECT status FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            return calculate_progress_pct(conn, job_id, str(row["status"]))
        finally:
            conn.close()

    def test_progress_uses_module_done_markers(self) -> None:
        running_job_id = self._create_job_with_logs(
            "running",
            ["MODULE_SCRAPER_DONE", "MODULE_DOM_MUTATOR_DONE"],
        )
        capped_running_job_id = self._create_job_with_logs(
            "running",
            [
                "MODULE_SCRAPER_DONE",
                "MODULE_DOM_MUTATOR_DONE",
                "MODULE_AI_REWRITER_DONE",
                "MODULE_MEDIA_UNIQUEIZER_DONE",
                "MODULE_PACKER_DONE",
                "MODULE_PACKER_DONE",  # duplicate marker must not exceed 90%
            ],
        )
        failed_job_id = self._create_job_with_logs(
            "failed",
            ["MODULE_SCRAPER_DONE", "MODULE_DOM_MUTATOR_DONE"],
        )
        done_job_id = self._create_job_with_logs("done", ["MODULE_SCRAPER_DONE"])
        pending_job_id = self._create_job_with_logs("pending", ["MODULE_SCRAPER_DONE"])

        self.assertEqual(self._get_progress_pct(running_job_id), 36)
        self.assertEqual(self._get_progress_pct(capped_running_job_id), 90)
        self.assertEqual(self._get_progress_pct(failed_job_id), 0)
        self.assertEqual(self._get_progress_pct(done_job_id), 100)
        self.assertEqual(self._get_progress_pct(pending_job_id), 0)


if __name__ == "__main__":
    unittest.main()
