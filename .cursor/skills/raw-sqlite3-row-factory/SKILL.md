---
name: raw-sqlite3-row-factory
description: Enforces raw sqlite3 stdlib usage with sqlite3.Row mapping and centralized Row→dict factories in models.py. Use for backend database access, database.py connection handling, models.py row conversion, SQL query changes, or whenever SQLite connection setup and row mapping are involved. Never use SQLAlchemy or any ORM.
---

# Raw SQLite3 Row Factory

## Rationale & Source Context
- **Category:** Backend / SQLite
- **PRD Directive:** §3.1 ARCH-DECISION: `database.py` uses `sqlite3.connect()` with `row_factory = sqlite3.Row`; `models.py` contains Row→dict factory functions for Pydantic schemas. SQLAlchemy/ORM is strictly forbidden.

## When to use
Use this skill when working on backend SQLite code, especially:
- Connection setup or refactors in `backend/database.py`
- Any code path creating DB connections (must be consistent everywhere)
- SQL query changes (CRUD, joins, progress queries)
- Row mapping and factory functions in `backend/models.py`
- API handlers/routers that read/write SQLite and convert rows to response shapes

## Non-negotiable rules
1. **Raw stdlib only:** Always use raw Python stdlib `sqlite3`. Never import SQLAlchemy or any ORM/query builder.
2. **Row Factory:** Set `conn.row_factory = sqlite3.Row` on every single connection.
3. **PRAGMAs:** Ensure every connection immediately applies project-required PRAGMAs:
   - `PRAGMA journal_mode=WAL;`
   - `PRAGMA foreign_keys=ON;`
4. **Centralized Mapping:** Keep Row-to-dict conversion centralized in `backend/models.py` factory functions. Convert rows via `dict(row)`.
5. **Security:** All SQL must be parameterized (`?` placeholders). **Never** use f-strings for SQL queries.

## Required implementation pattern

### Connection creation (`backend/database.py`)
- Open connections with `sqlite3.connect(...)`.
- Immediately configure the connection:
  - `conn.row_factory = sqlite3.Row`
  - Execute `PRAGMA journal_mode=WAL;`
  - Execute `PRAGMA foreign_keys=ON;`
- Do not return a connection without row factory + PRAGMAs configured.

### Data mapping (`backend/models.py`)
- Accept `sqlite3.Row` in factory functions.
- Convert with `dict(row)` as the first step.
- Build typed Pydantic models from that dictionary.

Example shape:
```python
import sqlite3
from schemas import User # Example Pydantic model

def user_from_row(row: sqlite3.Row) -> User:
    data = dict(row)
    return User(**data)