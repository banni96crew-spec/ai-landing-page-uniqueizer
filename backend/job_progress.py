import sqlite3

from backend.worker.runner import MODULE_DONE_MARKERS


def calculate_progress_pct(
    conn: sqlite3.Connection,
    job_id: int,
    status: str,
) -> int:
    if status in {"pending", "failed"}:
        return 0

    if status == "done":
        return 100

    if status != "running":
        return 0

    placeholders = ", ".join("?" for _ in MODULE_DONE_MARKERS)
    row = conn.execute(
        f"SELECT COUNT(*) AS done_count FROM logs "
        f"WHERE job_id = ? AND message IN ({placeholders})",
        (job_id, *MODULE_DONE_MARKERS),
    ).fetchone()
    progress = int(row["done_count"]) * 18
    return min(progress, 90)
