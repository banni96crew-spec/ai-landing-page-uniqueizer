# packer-zip-deflated-sha256-cleanup

```markdown
---
name: packer-zip-deflated-sha256-cleanup
description: Implements Module 5 packer using zipfile.ZipFile with ZIP_DEFLATED,
SHA256 hashing, artifacts pre-check (EC-17), OSError failure handling (EC-09), and
cleanup via shutil.rmtree after success. Use when editing
backend/worker/module_packer.py in Backend / Worker.
---
# packer-zip-deflated-sha256-cleanup

## When to use
Use this skill when working on:
- `backend/worker/module_packer.py`
- Module 5 (Packer)
- ZIP creation logic
- Artifact DB insertion
- EC-09 / EC-17 handling
- Cleanup of intermediate job directories

Applies only to **AI Landing Page Uniqueizer** worker.

---

## Rationale from PRD

§3.3, M7
EC-09 / EC-17

Requirements:
- Use `zipfile.ZipFile` with `ZIP_DEFLATED`
- Pack recursively from `rewritten/`
- Compute SHA256 using `hashlib`
- EC-17: use `INSERT OR IGNORE INTO artifacts` (atomic, no SELECT-before-write)
- EC-09: on `OSError` → set status='failed', log error, do NOT delete job directory
- Disk space check before packing: if `disk_free < estimated_size` → fail immediately
- After successful pack → `shutil.rmtree(job_dir)`
- Do NOT delete ZIP on failure
- Insert into `artifacts` table using field name `hash` (not `sha256_hash`)
- Set `jobs.status = 'done'` after successful artifact insert

---

## Required instruction

In `module_packer.py`:
- Check disk space before packing (PRD §2 MODULE_PACKER).
- Use `INSERT OR IGNORE INTO artifacts` for EC-17 (atomic, no race condition).
- Build zip from `rewritten_dir.rglob("*")` with `ZIP_DEFLATED`.
- Compute `hashlib.sha256`.
- On `OSError`: set `status='failed'`, log error, do NOT delete job directory.
- After successful pack + DB commit: `shutil.rmtree(job_dir, ignore_errors=True)`.
- Insert into artifacts table using field name `hash`.
- Update `jobs.status = 'done'` after successful insert.

---

## Non-negotiable rules
1. Use stdlib only: `zipfile`, `hashlib`, `shutil`.
2. Compression must be `ZIP_DEFLATED`.
3. Must recurse through entire `rewritten/`.
4. Must preserve relative paths inside archive.
5. Must compute SHA256 of final ZIP file.
6. Must use `INSERT OR IGNORE INTO artifacts` for EC-17 (NOT SELECT-before-write).
7. On `OSError` → mark job failed (EC-09), do NOT delete job directory.
8. Must not delete ZIP on failure.
9. Must cleanup intermediate directories only after success.
10. DB column name is `hash` (NOT `sha256_hash`).
11. Must check disk free space before packing.
12. Must set `jobs.status = 'done'` after successful artifact insert.

---

# Required implementation structure

## Step 1 — Disk space check
```python
from backend.config import ARTIFACTS_DIR
import shutil

rewritten_dir = job_dir / "rewritten"
zip_path = artifacts_dir / f"{job_id}.zip"

estimated_size = sum(
    f.stat().st_size
    for f in rewritten_dir.rglob("*")
    if f.is_file()
)
free = shutil.disk_usage(ARTIFACTS_DIR).free
if free < estimated_size:
    set_job_failed(job_id, "Insufficient disk space")
    log_error(job_id, "Insufficient disk space")
    return
```
- Must run BEFORE creating the ZIP.
- On failure: set `status='failed'`, log, return.
- Do NOT delete any directories.

---

## Step 2 — EC-17: Atomic artifact check via INSERT OR IGNORE
```python
conn.execute(
    """
    INSERT OR IGNORE INTO artifacts (job_id, file_path, file_size, hash)
    VALUES (?, ?, ?, ?)
    """,
    (job_id, str(zip_path), 0, ""),
)
conn.commit()

changes = conn.execute("SELECT changes()").fetchone()[0]
if changes == 0:
    # Record already exists — artifact was already packed
    existing = conn.execute(
        "SELECT file_path FROM artifacts WHERE job_id = ?",
        (job_id,),
    ).fetchone()
    return existing["file_path"]
```
- Must use `INSERT OR IGNORE` — atomic, no TOCTOU race condition.
- If `changes() == 0` → artifact exists, return existing path.
- Do NOT use SELECT-before-write pattern.

---

## Step 3 — Prepare paths
```python
rewritten_dir = job_dir / "rewritten"
zip_path = artifacts_dir / f"{job_id}.zip"
```
Output location must be:
```
/volumes/artifacts/{job_id}.zip
```

---

## Step 4 — Build ZIP (ZIP_DEFLATED)
```python
import zipfile
with zipfile.ZipFile(
    zip_path,
    "w",
    compression=zipfile.ZIP_DEFLATED,
) as zf:
    for path in rewritten_dir.rglob("*"):
        if path.is_file():
            arcname = path.relative_to(rewritten_dir)
            zf.write(path, arcname)
```
Rules:
- Must use `ZIP_DEFLATED`.
- Must use relative path inside archive.
- Must recurse via `rglob("*")`.

---

## Step 5 — Compute SHA256
```python
import hashlib

sha256 = hashlib.sha256()
with open(zip_path, "rb") as f:
    for chunk in iter(lambda: f.read(8192), b""):
        sha256.update(chunk)
hash_hex = sha256.hexdigest()
file_size = zip_path.stat().st_size
```

---

## Step 6 — Update artifact record + set jobs.status = 'done'
```python
conn.execute(
    """
    UPDATE artifacts
    SET file_path = ?, file_size = ?, hash = ?
    WHERE job_id = ?
    """,
    (str(zip_path), file_size, hash_hex, job_id),
)
conn.execute(
    "UPDATE jobs SET status = 'done' WHERE id = ?",
    (job_id,),
)
conn.commit()
```
- Must update the placeholder row created in Step 2.
- Must set `jobs.status = 'done'` in same transaction.
- Must use field name `hash`.

---

# EC-09 — OSError handling

Wrap disk check + ZIP build + hashing in:
```python
try:
    ...
except OSError as e:
    log_error(job_id, f"Disk space error: {str(e)}")
    set_job_failed(job_id, f"Disk space error: {str(e)}")
    # Do NOT call cleanup_job_workdir here
    # Failed job directories are preserved for debugging
    return
```
Rules:
- Set `jobs.status = 'failed'`
- Write error message
- Do NOT delete job directory (preserved for debugging per PRD policy)
- Do NOT delete ZIP if partially created
- Worker must not crash

---

# Cleanup after success

After successful DB commit:
```python
shutil.rmtree(job_dir, ignore_errors=True)
```
Must remove:
```
raw/
cleaned/
mutated/
rewritten/
```
Must not delete:
```
/volumes/artifacts/{job_id}.zip
```

---

# Correct execution order
1. Check disk free space
2. INSERT OR IGNORE into artifacts (EC-17 atomic check)
3. If changes() == 0 → return existing path (already packed)
4. Build ZIP (ZIP_DEFLATED)
5. Compute SHA256
6. UPDATE artifacts with real file_path, file_size, hash
7. UPDATE jobs SET status = 'done'
8. Commit
9. Cleanup job directory
10. Log `MARKER:packer_done`

---

# Prohibited patterns
- ❌ Using non-stdlib libraries
- ❌ Using different compression method
- ❌ Writing absolute paths into archive
- ❌ Skipping SHA256
- ❌ Using column `sha256_hash`
- ❌ Using SELECT-before-write for EC-17 (race condition)
- ❌ Deleting ZIP on failure
- ❌ Not handling OSError
- ❌ Cleaning artifacts directory
- ❌ Leaving intermediate dirs after success
- ❌ Deleting job directory on OSError (must preserve for debugging)
- ❌ Skipping disk space check
- ❌ Not setting jobs.status = 'done' after successful pack

---

# Definition of done
- Disk space checked before packing
- EC-17 implemented via `INSERT OR IGNORE` (atomic)
- ZIP built with `ZIP_DEFLATED`
- Files added via `rglob("*")`
- SHA256 computed via hashlib
- artifacts row updated with real hash, file_size, file_path
- jobs.status set to 'done'
- EC-09 implemented
- Job marked failed on OSError
- Job directory preserved on failure (not deleted)
- ZIP preserved on failure
- Intermediate job directory removed on success
- Worker remains stable
```