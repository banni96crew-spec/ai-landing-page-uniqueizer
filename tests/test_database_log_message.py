"""Tests for database.log_message DB + JOB_QUEUES broadcast integration."""

import asyncio
import tempfile
import unittest
from pathlib import Path

from backend import config, database
from backend.state import JOB_QUEUES, get_ws_broadcast_loop, set_ws_broadcast_loop


class LogMessageBroadcasterTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.previous_database_url = config.DATABASE_URL
        config.DATABASE_URL = str(self.db_path)
        JOB_QUEUES.clear()
        self._previous_loop = get_ws_broadcast_loop()
        database.init_db()

    def tearDown(self) -> None:
        set_ws_broadcast_loop(self._previous_loop)
        JOB_QUEUES.clear()
        config.DATABASE_URL = self.previous_database_url
        self.temp_dir.cleanup()

    def _create_job(self) -> int:
        conn = database.get_connection()
        try:
            cur = conn.execute(
                "INSERT INTO jobs (target_url, status) VALUES (?, ?)",
                ("https://example.com", "running"),
            )
            conn.commit()
            return int(cur.lastrowid)
        finally:
            conn.close()

    async def test_log_message_enqueues_after_insert(self) -> None:
        set_ws_broadcast_loop(asyncio.get_running_loop())
        job_id = self._create_job()
        JOB_QUEUES[job_id] = asyncio.Queue(maxsize=1000)
        conn = database.get_connection()
        try:
            database.log_message(conn, job_id, "warn", "disk almost full")
        finally:
            conn.close()

        await asyncio.sleep(0)
        item = JOB_QUEUES[job_id].get_nowait()
        self.assertEqual(item["job_id"], job_id)
        self.assertEqual(item["level"], "warn")
        self.assertEqual(item["message"], "disk almost full")
        self.assertTrue(str(item["timestamp"]))

    async def test_log_message_from_worker_thread(self) -> None:
        set_ws_broadcast_loop(asyncio.get_running_loop())
        job_id = self._create_job()
        JOB_QUEUES[job_id] = asyncio.Queue(maxsize=1000)

        def sync_log() -> None:
            conn = database.get_connection()
            try:
                database.log_message(conn, job_id, "info", "from_thread")
            finally:
                conn.close()

        await asyncio.to_thread(sync_log)
        await asyncio.sleep(0)
        item = await asyncio.wait_for(JOB_QUEUES[job_id].get(), timeout=2.0)
        self.assertEqual(item["message"], "from_thread")

    async def test_queue_full_drops_oldest(self) -> None:
        set_ws_broadcast_loop(asyncio.get_running_loop())
        job_id = self._create_job()
        JOB_QUEUES[job_id] = asyncio.Queue(maxsize=1)
        await JOB_QUEUES[job_id].put(
            {"job_id": job_id, "level": "info", "message": "stale", "timestamp": "t0"}
        )
        conn = database.get_connection()
        try:
            database.log_message(conn, job_id, "info", "fresh")
        finally:
            conn.close()

        await asyncio.sleep(0)
        self.assertEqual(JOB_QUEUES[job_id].qsize(), 1)
        item = JOB_QUEUES[job_id].get_nowait()
        self.assertEqual(item["message"], "fresh")

    async def test_no_queue_skips_broadcast_without_error(self) -> None:
        set_ws_broadcast_loop(asyncio.get_running_loop())
        job_id = self._create_job()
        conn = database.get_connection()
        try:
            database.log_message(conn, job_id, "info", "orphan")
        finally:
            conn.close()

        self.assertEqual(list(JOB_QUEUES.keys()), [])


if __name__ == "__main__":
    unittest.main()
