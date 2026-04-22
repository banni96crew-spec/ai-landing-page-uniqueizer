---
name: sqlite-wal-pragma-init
description: Enforces SQLite connection initialization rules for WAL mode, foreign key enforcement, and deterministic DB schema initialization via migrations/001_init.sql with inline-DDL fallback. Use for backend/database.py changes, connection handling, init_db()/get_connection() logic, lifespan startup initialization, or whenever SQLite PRAGMA setup and migrations execution are involved.
---

# SQLite WAL PRAGMA Init

## Source inputs (verbatim)
- Category (Stack) - Backend / SQLite
- Skill Name - sqlite-wal-pragma-init
- Rationale from PRD - §3.2 DDL: PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; обязательны при каждом init; миграция через migrations/001_init.sql с fallback inline-DDL в database.py.
- Specific Cursor instruction (prompt snippet) - In database.py, always execute PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; immediately after sqlite3.connect(). In lifespan, run conn.executescript(Path('migrations/001_init.sql').read_text()) with inline-DDL fallback if file missing.

## When to use
Use this skill when working on SQLite initialization and schema bootstrapping in the backend, especially:
- `backend/database.py` (`get_connection()`, `init_db()`, connection creation)
- Lifespan startup behavior in `backend/main.py` (anything that calls `init_db()` or touches DB init)
- Any refactor that could affect PRAGMA execution order, schema initialization, or migrations loading
- Debugging issues related to foreign keys not enforcing, locked database behavior, or missing tables/indexes/triggers

## Non-negotiable rules
1. In database.py, always execute PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; immediately after sqlite3.connect(). In lifespan, run conn.executescript(Path('migrations/001_init.sql').read_text()) with inline-DDL fallback if file missing.
2. Use only Python stdlib `sqlite3` for DB access (no SQLAlchemy/ORM).
3. Execute PRAGMAs on **every new connection** created by `get_connection()`:
   - `PRAGMA journal_mode=WAL`
   - `PRAGMA foreign_keys=ON`
4. `init_db()` must apply the schema by executing the full DDL from `migrations/001_init.sql` via `conn.executescript(...)`.
5. If `migrations/001_init.sql` is missing at runtime, `init_db()` must fallback to an `INLINE_DDL` constant that is **identical** to the migrations file content.
6. Do not introduce new migration tooling, ORMs, or schema managers; follow the project’s fixed architecture.

## Required implementation pattern

### Connection factory (`backend/database.py:get_connection()`)
- Create a sqlite3 connection.
- Immediately set the row factory as required by the project DB layer:
  - `conn.row_factory = sqlite3.Row`
- Immediately execute both PRAGMAs (order: connect → row_factory → PRAGMAs is acceptable; PRAGMAs must be immediately after connect, before any queries):
  - `PRAGMA journal_mode=WAL`
  - `PRAGMA foreign_keys=ON`
- Return the configured connection.

Minimal shape (illustrative):
```python
import sqlite3

def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn