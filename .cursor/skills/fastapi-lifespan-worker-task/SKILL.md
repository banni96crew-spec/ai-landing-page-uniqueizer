---
name: fastapi-lifespan-worker-task
description: Implements FastAPI lifespan startup/shutdown logic for worker initialization in the AI Landing Page Uniqueizer project. Use when editing backend/main.py, configuring application startup, initializing the database, wiring worker_loop, or handling EC-16 reset behavior.
---

# Backend / FastAPI

## Skill Name
fastapi-lifespan-worker-task

## Rationale from PRD
§3.1, §7.6: воркер стартует как asyncio.create_task(poll_loop()) внутри @asynccontextmanager async def lifespan(app). Дополнительно: asyncio.create_task(_ttl_cleanup_loop()). EC-16: при старте сбрасывать running→failed. Обе tasks отменяются в shutdown-ветке yield.

## Specific Cursor instruction
In main.py, define lifespan context manager: (1) call init_db(), (2) execute EC-16 reset SQL, (3) asyncio.create_task(poll_loop()), (4) asyncio.create_task(_ttl_cleanup_loop()). In shutdown branch after yield, cancel both tasks and await each with except CancelledError.

---

# FastAPI Lifespan Worker Task

## When to use

Use this skill when modifying:

- `backend/main.py`
- FastAPI app initialization
- Worker startup/shutdown behavior
- EC-16 reset logic
- Application lifecycle management

---

## Architectural Constraints (Non‑Negotiable)

1. Worker must start inside FastAPI lifespan context.
2. Worker must be launched using:
```python
from backend.worker.runner import poll_loop
worker_task = asyncio.create_task(poll_loop())
cleanup_task = asyncio.create_task(_ttl_cleanup_loop())
```
3. Both tasks must be cancelled on shutdown:
```python
worker_task.cancel()
cleanup_task.cancel()
for task in (worker_task, cleanup_task):
    try:
        await task
    except asyncio.CancelledError:
        pass
```
4. EC-16 reset must use exact error message from §3.1:
```python
conn.execute(
    "UPDATE jobs SET status='failed', "
    "error_message='Interrupted by server restart' "
    "WHERE status='running'"
)
```
5. Must NOT use `worker_loop()` — canonical function name per §3.1 is `poll_loop()`.
6. Must NOT omit `_ttl_cleanup_loop()` — required by §3.1.

---

## Required Implementation (§3.1 canonical — takes priority over §7.6)

```python
from contextlib import asynccontextmanager
from backend.database import init_db, get_connection
from backend.config import CORS_ORIGINS, ARTIFACT_TTL_DAYS, FAILED_JOB_TTL_DAYS
from backend.config import get_job_dir, get_artifact_path
import asyncio, shutil


async def _ttl_cleanup_loop():
    while True:
        await asyncio.sleep(86400)
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

    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET status='failed', "
        "error_message='Interrupted by server restart' "
        "WHERE status='running'"
    )
    conn.commit()
    conn.close()

    from backend.worker.runner import poll_loop
    worker_task = asyncio.create_task(poll_loop())
    cleanup_task = asyncio.create_task(_ttl_cleanup_loop())

    yield

    worker_task.cancel()
    cleanup_task.cancel()
    for task in (worker_task, cleanup_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
```