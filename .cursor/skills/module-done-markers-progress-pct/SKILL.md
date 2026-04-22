```markdown
---
name: module-done-markers-progress-pct
description: Enforces module completion markers and SQL-based progress calculation using COUNT(message IN MODULE_DONE_MARKERS) * 18. Use when editing backend/worker/runner.py, module success logging, or GET /api/jobs/{id} progress logic in Backend / Worker and Backend / FastAPI.
---
# module-done-markers-progress-pct

## When to use
Use this skill when working on:

- `backend/worker/runner.py`
- Module success logging
- `GET /api/jobs/{id}` endpoint
- Progress percentage calculation
- Logs table queries

Applies only to **AI Landing Page Uniqueizer** backend.

---

## Rationale from PRD

§4 M7.3  
§3.1

- Progress is calculated via:

```sql
SELECT COUNT(*) FROM logs
WHERE job_id = ?
AND message IN (MODULE_DONE_MARKERS)
```

- `progress_pct = count * 18`
- Exactly 5 module markers.
- pending → 0
- failed → 0
- done → 100

No other logic allowed.

---

## Required instruction

Define:

```python
MODULE_DONE_MARKERS = {
    "MODULE_SCRAPER_DONE",
    "MODULE_DOM_MUTATOR_DONE",
    "MODULE_AI_REWRITER_DONE",
    "MODULE_MEDIA_UNIQUEIZER_DONE",
    "MODULE_PACKER_DONE",
}
```

in `runner.py`.

In `GET /api/jobs/{id}`:

- Run:

```sql
SELECT COUNT(*) FROM logs
WHERE job_id = ?
AND message IN (...)
```

- Compute:

```
if done → 100
if pending or failed → 0
else → count * 18
```

Each module must log its marker string on success.

---

## Non-negotiable rules

1. Exactly 5 marker constants.
2. Must be defined as `set[str]`.
3. Must be defined in `backend/worker/runner.py`.
4. Modules must log marker string to `logs.message`.
5. Progress must be computed via SQL COUNT.
6. Must use parameterized query.
7. pending → 0.
8. failed → 0.
9. done → 100.
10. No intermediate states.
11. No dynamic weighting.
12. Do not compute progress in Python by counting in-memory logs.

---

# Required constant definition

In `backend/worker/runner.py`:

```python
  MODULE_DONE_MARKERS: set[str] = {
   "MARKER:scraper_done",
   "MARKER:mutator_done",
   "MARKER:rewriter_done",
   "MARKER:media_done",
   "MARKER:packer_done",
  }
```

Must match exactly:

- `MODULE_SCRAPER_DONE`
- `MODULE_DOM_MUTATOR_DONE`
- `MODULE_AI_REWRITER_DONE`
- `MODULE_MEDIA_UNIQUEIZER_DONE`
- `MODULE_PACKER_DONE`

No additional markers allowed.

---

# Module success logging

At the end of each module:

```python
log_info(job_id, "MODULE_SCRAPER_DONE")
```

Same for each module:

- Scraper
- DOM Mutator
- AI Rewriter
- Media Uniqueizer
- Packer

Marker must be logged only after successful completion.

---

# GET /api/jobs/{id} progress logic

## Step 1 — Fetch job row

```python
job = conn.execute(
    "SELECT status FROM jobs WHERE id = ?",
    (job_id,),
).fetchone()
```

---

## Step 2 — Terminal status override

```python
status = job["status"]

if status == "done":
    progress_pct = 100

elif status == "pending":
  progress_pct = 0
  else:
  # running or failed
      ...
```

Must check exact strings only.

---

## Step 3 — SQL count

```python
placeholders = ",".join("?" for _ in MODULE_DONE_MARKERS)

query = f"""
SELECT COUNT(*)
FROM logs
WHERE job_id = ?
AND message IN ({placeholders})
"""

row = conn.execute(
    query,
    (job_id, *MODULE_DONE_MARKERS),
).fetchone()

count = row[0]
progress_pct = count * 20
```

---

# Important behavior details

- While `running`, progress increments:
  - 1 marker → 18%
  - 2 markers → 36%
  - 3 markers → 54%
  - 4 markers → 72%
  - 5 markers → 90%
- When job.status becomes `'done'`:
  - Must return 100 (not 90)

---

# Prohibited patterns

- ❌ Computing progress from in-memory queue
- ❌ Counting non-marker log entries
- ❌ Using LIKE instead of IN
- ❌ Hardcoding count logic in Python
- ❌ Returning 90 when status='done'
- ❌ Returning non-zero for failed
- ❌ Adding extra markers
- ❌ Changing marker strings
- ❌ Using uppercase log levels incorrectly

---

# Definition of done

- `MODULE_DONE_MARKERS` defined exactly (5 entries)
- Each module logs its marker on success
- Progress computed via SQL COUNT
- pending → 0
- failed → 0
- done → 100
- running → count * 18
- No deviation from PRD calculation logic
- Worker and API consistent
```