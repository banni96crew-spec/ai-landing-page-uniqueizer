```markdown
---
name: atomic-job-claim-rowcount
description: Enforces atomic SQLite job claiming in the backend worker using SELECT * of a pending job followed by UPDATE jobs SET status='running' WHERE id=? AND status='pending', with cursor.rowcount == 1 validation. Returns full job dict (or None). Use when editing worker polling logic, claim_next_pending_job(), pending-job selection, or job status transition code in Backend / FastAPI.
---
# atomic-job-claim-rowcount

## When to use
Use this skill when working on:

- `backend/worker/runner.py`
- worker polling logic
- `claim_next_pending_job()`
- pending job selection
- atomic transition from `pending` to `running`
- concurrency-sensitive job claiming code

This skill applies to **AI Landing Page Uniqueizer** backend only.

---

## Non-negotiable rules

1. Valid job statuses are exactly: `pending`, `running`, `done`, `failed`.
2. Job claim must use atomic status transition:
   - first read a pending job candidate
   - then claim it with `UPDATE ... WHERE id=? AND status='pending'`
3. `cursor.rowcount == 1` is mandatory success validation.
4. If `cursor.rowcount == 0`, the job was already claimed — skip safely.
5. Do not introduce intermediate statuses.
6. Use raw stdlib `sqlite3` only — no ORM.
7. Use a single DB connection for SELECT + UPDATE.
8. Open connection as `conn = get_connection()` — do NOT use `with get_connection() as conn`.
9. Always call `conn.close()` explicitly before every `return`.
10. `claim_next_pending_job()` must return the **full job row as a dict** (or `None`) — NOT just an int.
11. SELECT must use `SELECT *` to include all fields needed by the caller (`id`, `target_url`, etc.).

---

## Required instruction

In `claim_next_pending_job()`: open with `conn = get_connection()`. Query the full pending job row with `SELECT *`. Attempt claim with `UPDATE ... WHERE id=? AND status='pending'`. If `rowcount == 0` (job already taken), call `conn.close()` and return `None` — no commit or rollback needed. If `rowcount == 1`, call `conn.commit()`, `conn.close()`, return the full job row as `dict(row)`.

---

## Return type

```python
def claim_next_pending_job() -> dict | None:
```

The caller in `runner.py` uses the return value as:

```python
job = claim_next_pending_job()
if job:
    job_id = job["id"]
    await run_pipeline(job_id, job["target_url"])
```

Returning only `job_id: int` will crash the caller on `job["id"]` and `job["target_url"]`.  
Always return `dict(row)` on success, or `None` on miss.

---

## Required implementation pattern

### Claim flow

1. Open one SQLite connection via `conn = get_connection()`.
2. Read one candidate: `SELECT *` with `status='pending'`, `ORDER BY created_at ASC`, `LIMIT 1` (PRD M1.2).
3. If no row found → `conn.close()`, return `None`.
4. Store `row` for later return, extract `job_id = row["id"]`.
5. Attempt atomic claim:
   ```sql
   UPDATE jobs
   SET status = 'running'
   WHERE id = ? AND status = 'pending'
   ```
6. If `rowcount == 0` → another worker claimed it first; `conn.close()`, return `None`.
7. If `rowcount == 1` → `conn.commit()`, `conn.close()`, return `dict(row)`.

> **[ARCH-DECISION: explicit conn.close(), not context manager]**  
> PRD `database.py` (строки 447–453) defines `get_connection()` as a plain function  
> returning `sqlite3.Connection` with no context manager wrapper. PRD's own usage  
> pattern (lifespan, строки 1857–1862) is always:  
> `conn = get_connection()` → `conn.execute(...)` → `conn.commit()` → `conn.close()`.  
>
> Using `with get_connection() as conn:` introduces two concrete bugs:  
> - **Success path**: manual `conn.commit()` runs, then `with __exit__` calls  
>   `conn.commit()` again — silent double-commit.  
> - **Skip path** (`rowcount == 0`): manual `conn.rollback()` runs, then `with __exit__`  
>   calls `conn.commit()` on the already-rolled-back transaction.  
> - In both paths `conn.close()` is never called — connection leak.  
>
> Always use explicit open/close: `conn = get_connection()` and `conn.close()` before every `return`.

> **[ARCH-DECISION: no rollback when rowcount == 0]**  
> When `rowcount == 0` the UPDATE matched no rows — nothing was written, no  
> transaction state was modified. Calling `conn.rollback()` in this path is  
> unnecessary and misleading. Simply call `conn.close()` and return `None`.

### Example shape

```python
def claim_next_pending_job() -> dict | None:
    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM jobs
        WHERE status = ?
        ORDER BY created_at ASC
        LIMIT 1
        """,
        ("pending",),
    ).fetchone()

    if row is None:
        conn.close()
        return None

    job_id = row["id"]

    cursor = conn.execute(
        """
        UPDATE jobs
        SET status = ?
        WHERE id = ? AND status = ?
        """,
        ("running", job_id, "pending"),
    )

    if cursor.rowcount != 1:
        # No rows changed — job already claimed by another worker.
        # Nothing was modified, so no commit or rollback is needed.
        conn.close()
        return None

    conn.commit()
    conn.close()
    return dict(row)
```

---

## Required SQL rules

- Always use parameterized queries with `?`
- Never use f-strings for SQL
- SELECT must be `SELECT *` — partial selects omit fields the caller requires
- Claim UPDATE must keep `AND status='pending'` in the `WHERE` clause
- Success is determined by `cursor.rowcount == 1`, not by assumptions from the SELECT

---

## Why this exists

The initial SELECT is only a candidate lookup — it does not reserve the row. The actual atomic claim happens only in the guarded UPDATE. The `rowcount` check prevents double-claim when multiple workers race for the same pending job (PRD EC-15).

---

## Prohibited patterns

- ❌ `UPDATE jobs SET status='running' WHERE id=?` without `AND status='pending'`
- ❌ Assuming the SELECT alone reserves the job
- ❌ Ignoring `cursor.rowcount`
- ❌ Treating `rowcount == 0` as an error that crashes the worker
- ❌ Using `with get_connection() as conn` (causes double-commit and connection leak)
- ❌ Forgetting `conn.close()` before any `return`
- ❌ Splitting SELECT and UPDATE across different DB connections
- ❌ Returning `int` (job_id only) instead of full job row dict
- ❌ Using `SELECT id` or any partial SELECT — caller needs `id`, `target_url`, and all other fields
- ❌ Calling `conn.rollback()` when `rowcount == 0` — nothing was modified, rollback is meaningless
- ❌ Using statuses like `processing`, `claimed`, or `completed`
- ❌ Using autocommit for the claim sequence
- ❌ Using ORM or non-stdlib DB layer

---

## Definition of done

- `claim_next_pending_job()` declares `-> dict | None`
- SELECT uses `SELECT *` to capture all fields
- UPDATE includes `WHERE id=? AND status='pending'`
- `cursor.rowcount == 1` checked explicitly
- `rowcount == 0` → `conn.close()`, `return None` (no commit, no rollback)
- `rowcount == 1` → `conn.commit()`, `conn.close()`, `return dict(row)`
- Single DB connection used for SELECT + UPDATE
- `conn = get_connection()` explicit open/close pattern throughout
- Only valid PRD statuses used: `pending`, `running`, `done`, `failed`
- No ORM or non-stdlib DB layer introduced
```
