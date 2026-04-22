```markdown
---
name: settings-api-key-masking-upsert
description: Implements GET /api/settings with API key masking and PUT /api/settings with validated INSERT OR REPLACE UPSERT logic. Use when editing backend/routers/settings.py, settings validation, or modifying settings persistence in Backend / FastAPI.
---
# settings-api-key-masking-upsert

## When to use
Use this skill when working on:

- `backend/routers/settings.py`
- GET `/api/settings`
- PUT `/api/settings`
- Settings validation logic
- Settings persistence (SQLite)

Applies only to **AI Landing Page Uniqueizer** backend.

---

## Rationale from PRD

§4 M6.1 / M6.2:

- GET `/api/settings` must mask API key values.
- Any key containing `_api_key` must return `"***"` instead of real value.
- PUT `/api/settings` performs batch `INSERT OR REPLACE`.
- Validation before write:
  - `noise_intensity ∈ [0.0, 0.01]`
  - `ai_provider ∈ {'openai', 'anthropic'}`
- On validation failure → HTTP 422.

---

## Required instruction

In GET `/api/settings`: for each setting, if `'_api_key'` in key replace value with `"***"`.  
In PUT `/api/settings`: before INSERT OR REPLACE, validate: `noise_intensity` float in `[0.0, 0.01]` else HTTP 422; `ai_provider` in `{'openai','anthropic'}` else HTTP 422.

---

## Non-negotiable rules

1. Use raw stdlib `sqlite3` via `get_connection()`.
2. Always use parameterized queries (`?`).
3. GET must never expose real API keys.
4. Masking rule: substring match `_api_key` (not exact equality).
5. PUT must validate before DB write.
6. Use `INSERT OR REPLACE` for batch UPSERT.
7. On validation error → raise `HTTPException(status_code=422, ...)`.
8. Do not introduce new setting keys.
9. Do not alter DB schema.

---

# GET /api/settings

## Required behavior

- Read all rows from `settings` table.
- For each row:
  - If `'_api_key' in key` → return `"***"` as value.
  - Otherwise return real value.

## Required implementation shape

```python
@router.get("/api/settings")
def get_settings():
    with get_connection() as conn:
        rows = conn.execute(
            "SELECT key, value FROM settings"
        ).fetchall()

    result = []

    for row in rows:
        key = row["key"]
        value = row["value"]

        if "_api_key" in key:
            value = "***"

        result.append({
            "key": key,
            "value": value,
        })

    return result
```

### Important

- Do NOT modify DB values.
- Masking happens only in response serialization.
- Substring check must be exact: `"_api_key" in key`.

---

# PUT /api/settings

## Required validation logic

Before any DB write:

### 1. noise_intensity

- Parse as float.
- Must satisfy: `0.0 <= value <= 0.01`
- Otherwise:

```python
raise HTTPException(status_code=422, detail="Invalid noise_intensity")
```

### 2. ai_provider

- Must be exactly one of:
  - `"openai"`
  - `"anthropic"`
- Otherwise:

```python
raise HTTPException(status_code=422, detail="Invalid ai_provider")
```

Validation must occur before `INSERT OR REPLACE`.

---

## Required UPSERT pattern

Batch write using:

```sql
INSERT OR REPLACE INTO settings (key, value, updated_at)
VALUES (?, ?, CURRENT_TIMESTAMP)
```

Example shape:

```python
@router.put("/api/settings")
def update_settings(payload: list[SettingUpdateRequest]):
    with get_connection() as conn:
        cursor = conn.cursor()

        for item in payload:
            key = item.key
            value = item.value

            if key == "noise_intensity":
                try:
                    parsed = float(value)
                except ValueError:
                    raise HTTPException(status_code=422, detail="Invalid noise_intensity")

                if not (0.0 <= parsed <= 0.01):
                    raise HTTPException(status_code=422, detail="Invalid noise_intensity")

            if key == "ai_provider":
                if value not in {"openai", "anthropic"}:
                    raise HTTPException(status_code=422, detail="Invalid ai_provider")

            cursor.execute(
                """
                INSERT OR REPLACE INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (key, value),
            )

        conn.commit()

    return {"updated": len(payload)}
```

---

## Prohibited patterns

- ❌ Returning real API key values
- ❌ Checking exact key equality instead of substring `_api_key`
- ❌ Writing to DB before validation
- ❌ Using f-strings for SQL
- ❌ Using ORM
- ❌ Allowing ai_provider values outside allowed set
- ❌ Allowing noise_intensity > 0.01
- ❌ Silent clamping instead of rejecting

---

## Definition of done

- GET masks all keys containing `_api_key`
- PUT validates `noise_intensity` range strictly
- PUT validates `ai_provider` membership strictly
- Validation errors return HTTP 422
- UPSERT uses `INSERT OR REPLACE`
- Raw sqlite3 only
- No API key leakage in responses
```