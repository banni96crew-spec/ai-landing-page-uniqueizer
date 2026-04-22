---
name: ec16-running-reset-on-startup
description: Implements EC-16 behavior to reset all running jobs to failed with error_message='Interrupted by server restart' during FastAPI lifespan startup, before launching worker and cleanup tasks. Use when editing backend/main.py lifespan logic in Backend / Worker.
---
# ec16-running-reset-on-startup

## When to use
Use this skill when working on:

- `backend/main.py`
- FastAPI lifespan startup logic
- Worker startup sequence
- EC-16 implementation
- GAP-M (no resume in MVP)

Applies only to **AI Landing Page Uniqueizer** backend.

---

## Rationale from PRD

§3.3 `backend/main.py` lifespan (canonical — Section 3 has highest priority per PRD conflict rule):

On container restart, before starting any tasks:

```sql
UPDATE jobs
SET status = 'failed',
    error_message = 'Interrupted by server restart'
WHERE status = 'running'
```

Must run during lifespan startup, before `poll_loop()` and `_ttl_cleanup_loop()` are launched.

GAP-M:

- Resume is NOT supported in MVP.
- Interrupted pipelines must not be resumed.

> **Priority note:** PRD §3.3 and §7.6 contain different values for `error_message` and worker function name.
> Per the PRD conflict rule (Section 3 > Section 4 > Section 2), §3.3 is authoritative.
> - `error_message` = `'Interrupted by server restart'` (§3.3), NOT `'Worker interrupted'` (§7.6).
> - Worker function = `poll_loop()` (§3.3), NOT `worker_loop()` (§7.6).

---

## Required instruction

In lifespan, after `init_db()` and before `asyncio.create_task(poll_loop())`:

- Open DB connection via `get_connection()`.
- Execute the reset SQL.
- Commit explicitly.
- Close connection explicitly via `conn.close()`.

Also launch `_ttl_cleanup_loop()` as a second background task alongside `poll_loop()`.
Cancel both tasks on shutdown.

Never attempt to resume interrupted pipelines — this is a known MVP limitation (GAP-M).

---

## Non-negotiable rules

1. Must execute before worker loop starts.
2. Must use raw `sqlite3` via `get_connection()` — no ORM.
3. Must commit transaction explicitly.
4. Must close connection explicitly via `conn.close()` — do NOT use `with get_connection() as conn` (sqlite3 context manager does not close the connection, only manages the transaction, causing a connection leak).
5. Must not attempt recovery or resume logic.
6. Must not retry or requeue interrupted jobs.
7. Must not introduce intermediate states.
8. Must not alter `done`, `pending`, or `failed` jobs.
9. `error_message` must be exactly: `'Interrupted by server restart'`.
10. Worker function name must be `poll_loop()`, imported from `backend.worker.runner`.
11. Both `worker_task` and `cleanup_task` must be cancelled and awaited on shutdown.

---

# Required implementation structure

## Full lifespan (canonical from §3.3)

```python
from contextlib import asynccontextmanager
from backend.database import init_db, get_connection
from backend.config import CORS_ORIGINS, ARTIFACT_TTL_DAYS, FAILED_JOB_TTL_DAYS
from backend.config import get_job_dir, get_artifact_path
import asyncio, shutil


async def _ttl_cleanup_loop():
    """Фоновая задача: удаляет устаревшие артефакты и директории failed-задач."""
    while True:
        await asyncio.sleep(86400)  # раз в 24 часа
        conn = get_connection()
        try:
            rows = conn.execute(
                "SELECT id FROM jobs WHERE status='done' "
                "AND updated_at < datetime('now', ?)",
                (f"-{ARTIFACT_TTL_DAYS} days",)
            ).fetchall()
            for row in rows:
                get_artifact_path(row["id"]).unlink(missing_ok=True)

            rows = conn.execute(
                "SELECT id FROM jobs WHERE status='failed' "
                "AND updated_at < datetime('now', ?)",
                (f"-{FAILED_JOB_TTL_DAYS} days",)
            ).fetchall()
            for row in rows:
                shutil.rmtree(get_job_dir(row["id"]), ignore_errors=True)
        finally:
            conn.close()


@asynccontextmanager
async def lifespan(app):
    init_db()

    # EC-16: reset interrupted jobs on restart
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET status='failed', "
        "error_message='Interrupted by server restart' "
        "WHERE status='running'"
    )
    conn.commit()
    conn.close()

    # Launch worker and TTL cleanup
    from backend.worker.runner import poll_loop
    worker_task  = asyncio.create_task(poll_loop())
    cleanup_task = asyncio.create_task(_ttl_cleanup_loop())

    yield

    # Shutdown: cancel both tasks
    worker_task.cancel()
    cleanup_task.cancel()
    for task in (worker_task, cleanup_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
```

---

## EC-16 reset block (isolated)

```python
conn = get_connection()
conn.execute(
    "UPDATE jobs SET status='failed', "
    "error_message='Interrupted by server restart' "
    "WHERE status='running'"
)
conn.commit()
conn.close()
```

Must:
- Use parameterless static SQL.
- Set `error_message` exactly: `'Interrupted by server restart'`
- Call `conn.close()` explicitly after commit.

---

# Correct execution order

1. `init_db()`
2. EC-16 reset block: `conn` open → execute → commit → `conn.close()`
3. `asyncio.create_task(poll_loop())` → `worker_task`
4. `asyncio.create_task(_ttl_cleanup_loop())` → `cleanup_task`
5. `yield` — application ready
6. On shutdown: cancel `worker_task`, cancel `cleanup_task`, await both in a loop

Never reorder steps 1–4.

---

# Why this exists

If container crashes while jobs are in `status = 'running'`, on restart they must become:

```
status        = 'failed'
error_message = 'Interrupted by server restart'
```

Resume logic is explicitly NOT supported (GAP-M).

---

# Prohibited patterns

- ❌ Attempting to resume pipeline from partial state
- ❌ Re-queueing interrupted jobs
- ❌ Leaving jobs in `'running'` after startup
- ❌ Running EC-16 reset after worker starts
- ❌ Skipping `conn.commit()`
- ❌ Using `with get_connection() as conn` — does not close the connection in sqlite3
- ❌ Skipping `conn.close()` — must be called explicitly
- ❌ Updating jobs unconditionally (without `WHERE status='running'`)
- ❌ Using ORM
- ❌ `error_message='Worker interrupted'` — §7.6 value, overridden by higher-priority §3.3
- ❌ `worker_loop()` — §7.6 name, overridden by higher-priority §3.3; correct is `poll_loop()`
- ❌ Launching only `worker_task` and omitting `cleanup_task`
- ❌ Cancelling only `worker_task` on shutdown without cancelling `cleanup_task`

---

# Definition of done

- All `status='running'` rows updated to `status='failed'` on startup ✅
- `error_message='Interrupted by server restart'` (§3.3 canonical value) ✅
- Reset runs before worker starts ✅
- Connection closed explicitly after commit via `conn.close()` ✅
- `poll_loop()` launched as `worker_task` ✅
- `_ttl_cleanup_loop()` launched as `cleanup_task` ✅
- Both tasks cancelled and awaited on shutdown ✅
- No resume logic implemented (GAP-M respected) ✅
- No unintended status changes to `done`, `pending`, or `failed` jobs ✅
