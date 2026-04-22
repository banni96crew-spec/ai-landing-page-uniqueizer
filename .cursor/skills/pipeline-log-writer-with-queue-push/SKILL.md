---
name: pipeline-log-writer-with-queue-push
description: Enforces unified log_message() helper defined in backend/database.py that writes to logs table first and then pushes structured log events into JOB_QUEUES for WebSocket broadcasting. Handles thread-safety for CPU-bound modules and FIFO queue dropping.
---
# pipeline-log-writer-with-queue-push

## When to use
Use this skill when working on:

- `backend/database.py`
- `backend/worker/runner.py`
- Worker modules (scraper, mutator, rewriter, media, packer)
- Logging utilities
- WebSocket log broadcasting
- `backend/ws/log_broadcaster.py`

Applies only to **AI Landing Page Uniqueizer** backend.

---

## Rationale from PRD

§3.1 & §3.3 WebSocket / Broadcaster:

- Every log must be persisted to SQLite BEFORE being broadcasted.
- `JOB_QUEUES` has a `maxsize=1000`. 
- If the queue is full, the oldest item must be dropped (FIFO) to make room for new logs.
- Modules 2 and 4 run in threads (`run_in_executor`), so the helper MUST be thread-safe for asyncio.

---

## Required instruction

Implement/use the `log_message` helper in `backend/database.py`. 

It must:
1. Insert the log into the `logs` table.
2. Retrieve the generated `timestamp` using `last_insert_rowid()` for consistency.
3. Commit the transaction immediately.
4. Use `loop.call_soon_threadsafe` to push to `asyncio.Queue` from any thread.
5. Implement the "drop-oldest-on-full" logic if `put_nowait` raises `QueueFull`.

---

## Non-negotiable rules

1. **DB First:** Never push to the queue without a successful DB commit.
2. **FIFO Logic:** If `JOB_QUEUES[job_id]` is full, `get_nowait()` the oldest item before pushing the new one.
3. **Thread-Safety:** Use `call_soon_threadsafe` to interact with `JOB_QUEUES` because logging often happens in background threads.
4. **Lowercase Levels:** Levels must be strictly `'info'`, `'warn'`, or `'error'`.
5. **No Manual Timestamps:** Let SQLite handle `CURRENT_TIMESTAMP`, then fetch it back.
6. **Parameterized SQL:** Always use `?` placeholders.

---

# Required implementation

## Helper function
Location: `backend/database.py`

```python
import sqlite3
import asyncio
from backend.state import JOB_QUEUES

def log_message(conn: sqlite3.Connection, job_id: int,
                level: str, message: str) -> None:
    # 1. DB Persistence
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO logs (job_id, level, message) VALUES (?, ?, ?)",
        (job_id, level, message)
    )
    # Efficiently fetch the generated timestamp
    cursor.execute("SELECT timestamp FROM logs WHERE id = ?", (cursor.lastrowid,))
    row = cursor.fetchone()
    timestamp = row["timestamp"] if row else ""
    conn.commit()

    # 2. Thread-safe WebSocket Broadcast
    if job_id in JOB_QUEUES:
        queue = JOB_QUEUES[job_id]
        item = {
            "job_id": job_id,
            "level": level,
            "message": message,
            "timestamp": timestamp,
        }

        def _push_to_queue():
            try:
                queue.put_nowait(item)
            except asyncio.QueueFull:
                try:
                    queue.get_nowait() # Drop oldest
                except asyncio.QueueEmpty:
                    pass
                queue.put_nowait(item)

        try:
            # Detect if we are in the main thread or a worker thread
            loop = asyncio.get_running_loop()
            loop.call_soon(_push_to_queue)
        except RuntimeError:
            # Fallback for CPU-bound modules (run_in_executor)
            loop = asyncio.get_event_loop()
            loop.call_soon_threadsafe(_push_to_queue)
```

---

# Usage in modules (mandatory)

All modules must import and use the helper:

```python
from backend.database import log_message

# Correct usage
log_message(conn, job_id, 'info', 'MARKER:scraper_done')
```

---

# Prohibited patterns

- ❌ Direct `JOB_QUEUES[id].put_nowait()` calls in modules.
- ❌ Direct `INSERT INTO logs` without updating the queue.
- ❌ Passing `datetime.now()` to the DB.
- ❌ Hardcoding `localhost` in log-related logic.
- ❌ Using `put()` (blocking) instead of `put_nowait()` inside the loop helper.
- ❌ Ignoring `QueueFull` exceptions (results in lost logs).

---

# Definition of done

- `log_message` handles both DB and Queue.
- Queue overflow is handled via FIFO (drop oldest).
- Logging is thread-safe (supports `run_in_executor`).
- Timestamp is fetched from DB after insert.
- Consistent lowercase levels used everywhere.
- Fully compliant with PRD §3.1, §3.2, and §3.3.
```