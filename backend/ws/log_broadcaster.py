from __future__ import annotations

import asyncio
from typing import TypedDict

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from backend import config
from backend.database import get_connection
from backend.routers.auth import validate_session_token_sync
from backend.state import JOB_QUEUES

router = APIRouter()

HISTORY_LIMIT = 500
JOB_NOT_FOUND_CLOSE_CODE = 4004
WS_AUTH_FAILED_CLOSE_CODE = 4401
QUEUE_POLL_TIMEOUT_SECONDS = 1.0
QUEUE_MISSING_RETRY_SECONDS = 0.2
TERMINAL_STATUSES = {"done", "failed"}


class LogEvent(TypedDict):
    level: str
    message: str
    timestamp: str


class JobSnapshot(TypedDict):
    status: str
    logs: list[LogEvent]


def _build_log_payload(level: str, message: str, timestamp: str) -> dict[str, str]:
    return {
        "type": "log",
        "level": level,
        "message": message,
        "timestamp": timestamp,
    }


def _load_job_snapshot_sync(job_id: int) -> JobSnapshot | None:
    conn = get_connection()
    try:
        job_row = conn.execute(
            "SELECT status FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if job_row is None:
            return None

        log_rows = conn.execute(
            """
            SELECT level, message, timestamp
            FROM (
                SELECT id, level, message, timestamp
                FROM logs
                WHERE job_id = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            ) AS recent_logs
            ORDER BY timestamp ASC, id ASC
            """,
            (job_id, HISTORY_LIMIT),
        ).fetchall()

        return {
            "status": str(job_row["status"]),
            "logs": [
                {
                    "level": str(row["level"]),
                    "message": str(row["message"]),
                    "timestamp": str(row["timestamp"]),
                }
                for row in log_rows
            ],
        }
    finally:
        conn.close()


def _load_job_status_sync(job_id: int) -> str | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT status FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return str(row["status"])
    finally:
        conn.close()


async def _load_job_snapshot(job_id: int) -> JobSnapshot | None:
    return await asyncio.to_thread(_load_job_snapshot_sync, job_id)


async def _load_job_status(job_id: int) -> str | None:
    return await asyncio.to_thread(_load_job_status_sync, job_id)


def _is_terminal_status(status: str | None) -> bool:
    return status in TERMINAL_STATUSES


def _queue_item_to_payload(item: object) -> dict[str, str]:
    if not isinstance(item, dict):
        raise TypeError("queue log item must be a dict")

    level = str(item.get("level", "info"))
    message = str(item.get("message", ""))
    timestamp = str(item.get("timestamp", ""))
    return _build_log_payload(level, message, timestamp)


async def _send_history(websocket: WebSocket, log_rows: list[LogEvent]) -> None:
    for log_row in log_rows:
        await websocket.send_json(
            _build_log_payload(
                log_row["level"],
                log_row["message"],
                log_row["timestamp"],
            )
        )


async def _send_terminal_message(websocket: WebSocket, status: str) -> None:
    await websocket.send_json({"type": "done", "status": status})


@router.websocket("/ws/logs/{job_id}")
async def stream_job_logs(websocket: WebSocket, job_id: int) -> None:
    token = websocket.cookies.get(config.AUTH_SESSION_COOKIE_NAME, "").strip()
    if not token:
        await websocket.close(code=WS_AUTH_FAILED_CLOSE_CODE)
        return
    try:
        await asyncio.to_thread(validate_session_token_sync, token)
    except HTTPException:
        await websocket.close(code=WS_AUTH_FAILED_CLOSE_CODE)
        return

    snapshot = await _load_job_snapshot(job_id)
    if snapshot is None:
        await websocket.close(code=JOB_NOT_FOUND_CLOSE_CODE)
        return

    try:
        await websocket.accept()
        await _send_history(websocket, snapshot["logs"])

        status = snapshot["status"]
        if _is_terminal_status(status):
            await _send_terminal_message(websocket, status)
            await websocket.close()
            return

        # TOCTOU (PRD): worker may have finished between snapshot load and accept;
        # queue is removed in runner finally — re-check before entering the live loop.
        if JOB_QUEUES.get(job_id) is None:
            refreshed = await _load_job_status(job_id)
            if refreshed is None:
                await _send_terminal_message(websocket, "failed")
                await websocket.close()
                return
            if _is_terminal_status(refreshed):
                await _send_terminal_message(websocket, refreshed)
                await websocket.close()
                return

        terminal_sent = False

        while True:
            queue = JOB_QUEUES.get(job_id)
            if queue is None:
                status = await _load_job_status(job_id)
                if status is None:
                    await websocket.close()
                    return
                if _is_terminal_status(status):
                    if not terminal_sent:
                        await _send_terminal_message(websocket, status)
                    await websocket.close()
                    return

                await asyncio.sleep(QUEUE_MISSING_RETRY_SECONDS)
                continue

            try:
                queue_item = await asyncio.wait_for(
                    queue.get(),
                    timeout=QUEUE_POLL_TIMEOUT_SECONDS,
                )
                await websocket.send_json(_queue_item_to_payload(queue_item))
            except asyncio.TimeoutError:
                pass

            status = await _load_job_status(job_id)
            if status is None:
                await websocket.close()
                return
            if _is_terminal_status(status):
                if not terminal_sent:
                    await _send_terminal_message(websocket, status)
                    terminal_sent = True
                await websocket.close()
                return
    except WebSocketDisconnect:
        return
