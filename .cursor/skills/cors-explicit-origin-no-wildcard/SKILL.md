```markdown
---
name: cors-explicit-origin-no-wildcard
description: Enforces explicit CORS configuration in FastAPI with fixed localhost origins and forbids wildcard "*" to prevent security misconfiguration when port 8000 is exposed. Use when editing backend/main.py CORS setup in DevOps / Docker.
---
# cors-explicit-origin-no-wildcard

## When to use
Use this skill when working on:

- `backend/main.py`
- FastAPI app initialization
- CORS configuration
- Deployment security configuration

Applies only to **AI Landing Page Uniqueizer** backend.

---

## Rationale from PRD

§7.3 ARCH-DECISION:

- Use `CORSMiddleware`
- Explicit origins only:
  ```python
  ["http://localhost:3000", "http://127.0.0.1:3000"]
  ```
- Wildcard `"*"` is explicitly forbidden
- Prevents security misconfiguration when port 8000 is exposed

---

## Required instruction

In `main.py`, add `CORSMiddleware` with:

```python
allow_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
```

Never use:

```python
allow_origins=["*"]
```

Methods:

```python
["GET","POST","PUT","DELETE","OPTIONS"]
```

Headers:

```python
["Content-Type","Authorization"]
```

`allow_credentials=True`

---

## Non-negotiable rules

1. Must use `CORSMiddleware`.
2. Must define explicit origins only.
3. Must never use `"*"`.
4. Must set `allow_credentials=True`.
5. Must define allowed methods explicitly.
6. Must define allowed headers explicitly.
7. Must not allow all headers.
8. Must not allow all methods.
9. Must not dynamically inject origins from request.
10. Must not expose backend to arbitrary origins.

---

# Required implementation

## Import

```python
from fastapi.middleware.cors import CORSMiddleware
```

---

## Middleware configuration

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
```

Must match exactly.

---

# Why wildcard is forbidden

Incorrect:

```python
allow_origins=["*"]
```

Risk:

- If port 8000 exposed publicly
- Any malicious origin can send authenticated requests
- Credentials + wildcard = security vulnerability

PRD explicitly forbids this configuration.

---

# Correct security model

Allowed:

- Local development frontend:
  - `http://localhost:3000`
  - `http://127.0.0.1:3000`

Not allowed:

- `*`
- Production domains unless explicitly added
- Dynamic origin reflection

---

# Prohibited patterns

- ❌ `allow_origins=["*"]`
- ❌ `allow_origins=["http://*"]`
- ❌ `allow_headers=["*"]`
- ❌ `allow_methods=["*"]`
- ❌ Removing `allow_credentials=True`
- ❌ Adding runtime origin reflection
- ❌ Omitting CORS entirely
- ❌ Using custom CORS middleware

---

# Definition of done

- `CORSMiddleware` configured in `main.py`
- `allow_origins` contains exactly:
  - `http://localhost:3000`
  - `http://127.0.0.1:3000`
- No wildcard used
- `allow_credentials=True`
- Methods explicitly defined
- Headers explicitly defined
- Fully compliant with PRD §7.3 ARCH-DECISION
```