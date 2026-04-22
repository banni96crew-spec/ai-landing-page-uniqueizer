```markdown
---
name: artifact-download-fileresponse-filename
description: Implements GET /api/artifacts/{job_id}/download using FileResponse with deterministic filename uniqueized_{job_id}_{jobs_created_at[:10]}.zip and strict status/file checks. Use when editing backend/routers/artifacts.py or artifact download logic in Backend / FastAPI.
---
# artifact-download-fileresponse-filename

## When to use
Use this skill when working on:

- `backend/routers/artifacts.py`
- GET `/api/artifacts/{job_id}/download`
- Artifact file serving logic
- FileResponse construction
- Status-based access control for downloads

Applies only to **AI Landing Page Uniqueizer** backend.

---

## Rationale from PRD

§3.1, GAP-J, M7.1, M7.2:

- Endpoint: GET `/api/artifacts/{job_id}/download`
- Must return `FileResponse`
- `media_type='application/zip'`
- Filename format:
  ```
  uniqueized_{job_id}_{jobs_created_at[:10]}.zip
  ```
- If `jobs.status != 'done'` → return:
  ```
  409 {"detail": "Job not completed", "current_status": status}
  ```
- If file missing on disk → return:
  ```
  500 {"detail": "Artifact file missing from disk"}
  ```

---

## Required instruction

In `artifacts.py`: open connection as `conn = get_connection()`, fetch job row, if status != 'done' close conn and return `JSONResponse(status_code=409, content={"detail": "Job not completed", "current_status": status})`. If file_path missing on disk close conn and raise 500. Else close conn and return `FileResponse(path, media_type='application/zip', filename=f'uniqueized_{job_id}_{job["created_at"][:10]}.zip')`. Always call `conn.close()` explicitly before every return or raise.

---

## Non-negotiable rules

1. Use raw `sqlite3` via `get_connection()`.
2. Always use parameterized queries (`?`).
3. Open connection as `conn = get_connection()` — do NOT use `with get_connection() as conn`.
4. Always call `conn.close()` explicitly before every `return` or `raise` in the handler.
5. Status must be checked against exact value `'done'`.
6. Valid job statuses are only: `pending`, `running`, `done`, `failed`.
7. Must return 404 if job does not exist.
8. Must return 409 if job not completed — use `JSONResponse`, NOT `HTTPException`, to avoid double-nested `detail` key.
9. Must return 500 if artifact file missing on disk.
10. Must use `FileResponse` for the success path.
11. `media_type` must be exactly `'application/zip'`.

---

# Required implementation flow

## Step 1 — Open connection and fetch job

```python
conn = get_connection()

job = conn.execute(
    "SELECT id, status, created_at FROM jobs WHERE id = ?",
    (job_id,),
).fetchone()

if job is None:
    conn.close()
    raise HTTPException(status_code=404, detail="Job not found")
```

Always call `conn.close()` before raising or returning.

---

## Step 2 — Validate status

Return a `JSONResponse` directly — do NOT use `HTTPException`:

```python
from fastapi.responses import JSONResponse

if job["status"] != "done":
    conn.close()
    return JSONResponse(
        status_code=409,
        content={
            "detail": "Job not completed",
            "current_status": job["status"],
        },
    )
```

> **[ARCH-DECISION: JSONResponse, not HTTPException for 409]**  
> PRD (§3.1, строка 1600) specifies the exact response body:  
> `{"detail": "Job not completed", "current_status": str}`  
> Using `HTTPException(detail={"detail": ..., "current_status": ...})` causes  
> FastAPI to serialize it as `{"detail": {"detail": ..., "current_status": ...}}` —  
> double-nested, which violates the PRD contract. `JSONResponse` writes the content  
> dict directly as the response body without wrapping it in a `"detail"` key.

Response body must be exactly:
```json
{"detail": "Job not completed", "current_status": "<status>"}
```

Do not use other wording. Do not nest inside another `"detail"` key.

---

## Step 3 — Fetch artifact record

```python
artifact = conn.execute(
    "SELECT file_path FROM artifacts WHERE job_id = ?",
    (job_id,),
).fetchone()
```

If no artifact row exists → treat as missing file → 500.

---

## Step 4 — Validate file exists on disk

```python
import os

file_path = artifact["file_path"] if artifact else None

if not file_path or not os.path.exists(file_path):
    conn.close()
    raise HTTPException(
        status_code=500,
        detail="Artifact file missing from disk",
    )
```

Error message must match exactly:
```
"Artifact file missing from disk"
```

---

## Step 5 — Close connection and return FileResponse

Close the connection before returning the response:

```python
conn.close()
```

> **[ARCH-DECISION: explicit conn.close(), not context manager]**  
> PRD `database.py` defines `get_connection()` as a plain function returning  
> `sqlite3.Connection` with no context manager wrapper. PRD's own usage pattern  
> (lifespan, строки 1857–1862) is always:  
> `conn = get_connection()` → `conn.execute(...)` → `conn.commit()` → `conn.close()`.  
> Using `with get_connection() as conn:` deviates from this pattern and creates  
> structural ambiguity when the same `conn` is needed across multiple sequential  
> steps. Always close explicitly after all queries in the handler are complete.

Filename must be derived from `jobs.created_at` using a string slice:

```python
filename = f"uniqueized_{job_id}_{job['created_at'][:10]}.zip"
```

> **[ARCH-DECISION: [:10] slice, not strftime]**  
> PRD contains an internal conflict:  
> - §3.1 (строка 274) comment uses `.strftime('%Y-%m-%d')` — implies a datetime object  
> - M7.2 (строка 1211) explicitly states: `jobs.created_at[:10]` (первые 10 символов ISO-строки)  
>
> **Resolution: follow M7.2.** SQLite with raw sqlite3 returns `created_at` as a  
> plain text string (e.g. `"2026-04-19 12:00:00"`). No datetime parsing occurs.  
> Slicing `[:10]` is correct, dependency-free, and explicitly specified in M7.2,  
> which is the more specific and authoritative reference.

Return:

```python
from fastapi.responses import FileResponse

return FileResponse(
    file_path,
    media_type="application/zip",
    filename=filename,
)
```

---

## Critical formatting rules

- Date is derived from `jobs.created_at[:10]` — string slice only
- Do NOT parse date into a datetime object
- Do NOT use `.strftime()`
- Do NOT use current date
- Do NOT change filename pattern
- Do NOT use artifact table timestamp

Correct example:
```
uniqueized_12_2026-04-19.zip
```

---

## Prohibited patterns

- ❌ Allowing download when status != 'done'
- ❌ Returning 400 instead of 409
- ❌ Returning 404 when job exists but is not done
- ❌ Using `HTTPException` for 409 (produces double-nested `detail` key)
- ❌ Using current date instead of `jobs.created_at`
- ❌ Omitting `"current_status"` in 409 response
- ❌ Serving file without existence check
- ❌ Using non-zip media type
- ❌ Using ORM
- ❌ Using `with get_connection() as conn` context manager pattern
- ❌ Forgetting `conn.close()` before any return or raise
- ❌ Using `.strftime()` to format the date

---

## Definition of done

- 404 if job not found; `conn.close()` called before raise
- 409 via `JSONResponse` with exact flat structure `{"detail": "Job not completed", "current_status": "..."}` if status != 'done'
- 500 with exact message `"Artifact file missing from disk"` if file missing; `conn.close()` called before raise
- Deterministic filename based on `jobs.created_at[:10]` string slice
- `FileResponse` with `media_type='application/zip'`
- Raw sqlite3 only, `conn = get_connection()` explicit open/close pattern
- `conn.close()` called before every return and raise path
```
