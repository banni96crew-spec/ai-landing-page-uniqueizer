---
name: pipeline-runner-match-case-status-machine
description: Enforces sequential pipeline execution in worker_loop with strict 4-state job status machine (pending|running|done|failed) and module progress tracked only via logs table markers. Use when editing backend/worker/runner.py in Integrations / Pipeline.
---
# pipeline-runner-match-case-status-machine

## When to use
Use this skill when working on:

- `backend/worker/runner.py`
- `worker_loop()`
- `run_pipeline()`
- Module orchestration
- Job lifecycle management
- Status transitions

Applies only to **AI Landing Page Uniqueizer** worker.

---

## Rationale from PRD

§2 & §4 (M1):

- Worker is a single `while True` loop polling the DB.
- Modules executed sequentially for each job.
- `jobs.status` accepts strictly:
  - `pending`
  - `running`
  - `done`
  - `failed`
- Intermediate progress tracked ONLY via:
  - `logs` table
  - `MODULE_*_DONE` markers
- The word `'completed'` is NEVER used.
- Pipeline must enforce `JOB_TIMEOUT_SECONDS` via `asyncio.wait_for`.

---

## Required instruction

In `runner.py`:

- Implement `run_pipeline(job_id, target_url)` as sequential `await` calls to each module.
- Worker loop:
  - `while True`
  - claim job
  - create Queue with `maxsize=1000`
  - await pipeline wrapped in `asyncio.wait_for`
  - pop Queue in `finally`
- Handle `asyncio.TimeoutError` explicitly to set `status='failed'`.
- Never write intermediate status values like:
  - `'scraping'`
  - `'completed'`
  - `'processing'`
  - `'mutating'`
  - to `jobs.status`.

---

## Non-negotiable rules

1. Status values: `pending`, `running`, `done`, `failed`. Nothing else.
2. Never use `'completed'`.
3. Pipeline modules run strictly sequentially.
4. Module-level progress only through logs.
5. Worker loop never crashes.
6. Top-level `try/except` wraps entire pipeline execution in the worker loop.
7. Queue per job created BEFORE pipeline with `maxsize=1000`.
8. Queue removed in `finally` block AFTER terminal state.
9. Single async polling loop for fetching jobs.
10. No external scheduler, no Celery, no APScheduler.

---

# Required worker_loop structure

```python
import asyncio
import logging
from backend.state import JOB_QUEUES
from backend.config import WORKER_POLL_INTERVAL, JOB_TIMEOUT_SECONDS

async def worker_loop():
    while True:
        try:
            job = claim_next_pending_job() # Atomic UPDATE + SELECT

            if job is None:
                await asyncio.sleep(WORKER_POLL_INTERVAL)
                continue

            job_id = job["id"]
            
            # CRITICAL: maxsize=1000 to prevent OOM
            JOB_QUEUES[job_id] = asyncio.Queue(maxsize=1000)

            try:
                # CRITICAL: Enforce pipeline timeout
                await asyncio.wait_for(
                    run_pipeline(job_id, job["target_url"]),
                    timeout=JOB_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                _mark_failed(job_id, f"Pipeline timeout after {JOB_TIMEOUT_SECONDS}s")
            except Exception as e:
                _mark_failed(job_id, str(e))
            finally:
                JOB_QUEUES.pop(job_id, None)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logging.error(f"Worker loop unexpected error: {e}")
            await asyncio.sleep(WORKER_POLL_INTERVAL)
```

---

# Required run_pipeline structure

```python
async def run_pipeline(job_id: int, target_url: str) -> None:
    # Modules must run strictly sequentially
    await module_scraper.run(job_id, target_url)
    await module_dom_mutator.run(job_id)
    await module_ai_rewriter.run(job_id)
    await module_media.run(job_id)
    await module_packer.run(job_id)

    _mark_done(job_id)
```

Rules:

- Sequential `await` calls.
- Final state set explicitly upon successful completion.
- Exceptions bubble up to be caught by the `worker_loop`'s `try/except`.

---

# Status transition rules

Allowed transitions:

```
pending → running
running → done
running → failed
```

Forbidden:

```
running → completed   ❌
running → processing  ❌
pending → done        ❌
done → anything       ❌
failed → anything     ❌
```

---

# Module progress tracking

Only via logs table:

```python
log_message(conn, job_id, 'info', "MODULE_SCRAPER_DONE")
log_message(conn, job_id, 'info', "MODULE_DOM_MUTATOR_DONE")
log_message(conn, job_id, 'info', "MODULE_AI_REWRITER_DONE")
log_message(conn, job_id, 'info', "MODULE_MEDIA_UNIQUEIZER_DONE")
log_message(conn, job_id, 'info', "MODULE_PACKER_DONE")
```

Never store intermediate progress in `jobs.status`.

---

# Queue lifecycle

Required:

```python
JOB_QUEUES[job_id] = asyncio.Queue(maxsize=1000)  # before pipeline
...
JOB_QUEUES.pop(job_id, None)                      # in finally
```

Rules:

- Queue created BEFORE pipeline.
- Queue MUST have `maxsize=1000`.
- Queue removed AFTER terminal state.
- Always inside `finally` block.

---

# Error handling philosophy

- All exceptions caught.
- Worker loop never dies.
- Job → `failed` with `error_message=str(e)` on module exception.
- Job → `failed` with timeout message on `TimeoutError`.
- `asyncio.CancelledError` re-raised only.

---

# Prohibited patterns

- ❌ Using `'completed'`
- ❌ Using `'scraping'`, `'processing'`, `'mutating'`
- ❌ Parallel module execution WITHIN a single job (modules must be sequential)
- ❌ Breaking WORKER_CONCURRENCY logic (parallel tasks are allowed up to the concurrency limit, but a single job's pipeline is strictly sequential)
- ❌ Scheduling via Celery/ARQ/APScheduler
- ❌ Allowing exceptions to crash worker_loop
- ❌ Defining JOB_QUEUES outside of `backend/state.py`
- ❌ Updating jobs.status to track stage
- ❌ Writing progress numbers into jobs table

---

# Definition of done

- Worker loop runs indefinitely
- Pipeline executes modules sequentially
- Pipeline respects `JOB_TIMEOUT_SECONDS`
- Only 4 statuses ever written to jobs.status
- Module progress tracked exclusively via logs markers
- Worker never crashes
- Queue properly created with limit and cleaned
- `'completed'` does not exist anywhere
- Fully compliant with PRD §2 and v1.5 architectural decisions
```

