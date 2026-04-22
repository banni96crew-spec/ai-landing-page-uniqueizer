---
name: per-job-asyncio-queue-singleton
description: Enforces the per-job asyncio.Queue singleton pattern defined in state.py for the AI Landing Page Uniqueizer project. Use when modifying backend/state.py, worker/runner.py, or ws/log_broadcaster.py to ensure JOB_QUEUES is defined once, imported correctly, and managed without circular imports.
---

# Backend / FastAPI

## Skill Name
per-job-asyncio-queue-singleton

## Rationale from PRD
§3.1, GAP-C/D, §7.6: JOB_QUEUES: dict[int, asyncio.Queue] = {} is defined in state.py as a module-level singleton. It is imported via `from backend.state import JOB_QUEUES` in runner.py and ws/log_broadcaster.py — without circular import.

## Specific Cursor instruction
Define JOB_QUEUES: dict[int, asyncio.Queue] = {} only in state.py. In runner.py: before pipeline start JOB_QUEUES[job_id] = asyncio.Queue(), after finish JOB_QUEUES.pop(job_id, None). Both runner.py and log_broadcaster.py import it via from backend.state import JOB_QUEUES. Never redefine it elsewhere.

---

# Per-Job asyncio Queue Singleton

## Purpose

Provide a single in-memory registry of per-job asyncio queues for WebSocket log streaming and worker communication.

Each job gets exactly one queue during processing.

---

## Authoritative Definition Location

Must exist only in:

`backend/state.py`

```python
# backend/state.py
# ЕДИНСТВЕННАЯ точка определения JOB_QUEUES.
# Все модули импортируют отсюда.
# Недопустимо определять JOB_QUEUES в main.py или любом другом модуле.
import asyncio

JOB_QUEUES: dict[int, asyncio.Queue] = {}
```
