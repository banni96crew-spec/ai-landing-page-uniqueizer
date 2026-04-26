import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import WebSocketDisconnect

from backend import config, database
from backend.state import JOB_QUEUES
from backend.ws import log_broadcaster


class FakeWebSocket:
    def __init__(self, *, disconnect_on_send: bool = False) -> None:
        self.disconnect_on_send = disconnect_on_send
        self.accepted = False
        self.closed = False
        self.close_code: int | None = None
        self.sent_messages: list[dict[str, str]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, payload: dict[str, str]) -> None:
        if self.disconnect_on_send:
            raise WebSocketDisconnect()
        self.sent_messages.append(payload)

    async def close(self, code: int = 1000) -> None:
        self.closed = True
        self.close_code = code


class LogBroadcasterTests(unittest.IsolatedAsyncioTestCase):
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

    def _create_job(self, status: str) -> int:
        conn = database.get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO jobs (target_url, status) VALUES (?, ?)",
                ("https://example.com", status),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def _insert_logs(self, job_id: int, logs: list[tuple[str, str, str]]) -> None:
        conn = database.get_connection()
        try:
            conn.executemany(
                """
                INSERT INTO logs (job_id, level, message, timestamp)
                VALUES (?, ?, ?, ?)
                """,
                [(job_id, level, message, timestamp) for level, message, timestamp in logs],
            )
            conn.commit()
        finally:
            conn.close()

    def _update_job_status(self, job_id: int, status: str) -> None:
        conn = database.get_connection()
        try:
            conn.execute(
                "UPDATE jobs SET status = ? WHERE id = ?",
                (status, job_id),
            )
            conn.commit()
        finally:
            conn.close()

    async def test_missing_job_closes_with_4004(self) -> None:
        websocket = FakeWebSocket()

        await log_broadcaster.stream_job_logs(websocket, 999999)

        self.assertFalse(websocket.accepted)
        self.assertTrue(websocket.closed)
        self.assertEqual(websocket.close_code, log_broadcaster.JOB_NOT_FOUND_CLOSE_CODE)
        self.assertEqual(websocket.sent_messages, [])

    async def test_terminal_job_replays_history_then_sends_done(self) -> None:
        job_id = self._create_job("done")
        self._insert_logs(
            job_id,
            [
                ("info", "first", "2026-01-01 00:00:01"),
                ("warn", "second", "2026-01-01 00:00:02"),
            ],
        )
        websocket = FakeWebSocket()

        await log_broadcaster.stream_job_logs(websocket, job_id)

        self.assertTrue(websocket.accepted)
        self.assertTrue(websocket.closed)
        self.assertEqual(
            websocket.sent_messages,
            [
                {
                    "type": "log",
                    "level": "info",
                    "message": "first",
                    "timestamp": "2026-01-01 00:00:01",
                },
                {
                    "type": "log",
                    "level": "warn",
                    "message": "second",
                    "timestamp": "2026-01-01 00:00:02",
                },
                {"type": "done", "status": "done"},
            ],
        )

    async def test_toctou_stale_running_snapshot_terminal_in_db(self) -> None:
        """Stale snapshot says running; DB already done and queue removed (TOCTOU)."""
        job_id = self._create_job("running")
        self._insert_logs(
            job_id,
            [("info", "history", "2026-01-01 00:00:01")],
        )
        self._update_job_status(job_id, "done")
        stale_snapshot: log_broadcaster.JobSnapshot = {
            "status": "running",
            "logs": [
                {
                    "level": "info",
                    "message": "history",
                    "timestamp": "2026-01-01 00:00:01",
                }
            ],
        }
        websocket = FakeWebSocket()

        with mock.patch.object(
            log_broadcaster,
            "_load_job_snapshot",
            new=mock.AsyncMock(return_value=stale_snapshot),
        ):
            await log_broadcaster.stream_job_logs(websocket, job_id)

        self.assertTrue(websocket.accepted)
        self.assertTrue(websocket.closed)
        self.assertEqual(
            websocket.sent_messages,
            [
                {
                    "type": "log",
                    "level": "info",
                    "message": "history",
                    "timestamp": "2026-01-01 00:00:01",
                },
                {"type": "done", "status": "done"},
            ],
        )

    async def test_running_job_streams_queue_item_then_done(self) -> None:
        job_id = self._create_job("running")
        self._insert_logs(
            job_id,
            [("info", "history", "2026-01-01 00:00:01")],
        )
        JOB_QUEUES[job_id] = asyncio.Queue(maxsize=1000)
        websocket = FakeWebSocket()

        broadcaster_task = asyncio.create_task(
            log_broadcaster.stream_job_logs(websocket, job_id)
        )

        await asyncio.sleep(0.05)
        await JOB_QUEUES[job_id].put(
            {
                "level": "info",
                "message": "live",
                "timestamp": "2026-01-01 00:00:02",
            }
        )
        await asyncio.sleep(0.05)
        self._update_job_status(job_id, "done")

        await asyncio.wait_for(broadcaster_task, timeout=2.0)

        self.assertEqual(
            websocket.sent_messages,
            [
                {
                    "type": "log",
                    "level": "info",
                    "message": "history",
                    "timestamp": "2026-01-01 00:00:01",
                },
                {
                    "type": "log",
                    "level": "info",
                    "message": "live",
                    "timestamp": "2026-01-01 00:00:02",
                },
                {"type": "done", "status": "done"},
            ],
        )
        self.assertTrue(websocket.closed)

    async def test_disconnect_during_history_replay_is_silent(self) -> None:
        job_id = self._create_job("done")
        self._insert_logs(
            job_id,
            [("info", "history", "2026-01-01 00:00:01")],
        )
        websocket = FakeWebSocket(disconnect_on_send=True)

        await log_broadcaster.stream_job_logs(websocket, job_id)

        self.assertTrue(websocket.accepted)
        self.assertFalse(websocket.closed)
        self.assertEqual(websocket.sent_messages, [])


if __name__ == "__main__":
    unittest.main()
