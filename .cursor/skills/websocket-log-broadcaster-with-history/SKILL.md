```markdown
---
name: websocket-log-broadcaster-with-history
description: Implements WebSocket log streaming with initial history replay and per-job queue polling using asyncio.wait_for. Use when editing ws/log_broadcaster.py, WebSocket /ws/logs/{job_id} handling, JOB_QUEUES integration, or log streaming behavior in Backend / FastAPI.
---
# websocket-log-broadcaster-with-history

## When to use
Use this skill when working on:

- `backend/ws/log_broadcaster.py`
- WebSocket endpoint `/ws/logs/{job_id}`
- JOB_QUEUES integration
- Log streaming logic
- Handling WebSocketDisconnect
- Replaying logs from `logs` table

Applies only to **AI Landing Page Uniqueizer** backend.

---

## Rationale from PRD

§3.1 WebSocket spec:
- On connect → first send full history from `logs` table.
- Then stream new logs from `JOB_QUEUES[job_id]`.
- Use `asyncio.wait_for(queue.get(), timeout=1.0)`.
- Final message format:
  ```json
  {"type": "done", "status": "done|failed"}
  ```

EC-18:
- On `WebSocketDisconnect` → silently close.
- Never interrupt worker pipeline.

---

## Required instruction

In log_broadcaster.py:  
(1) validate job exists else reject,  
(2) send all historical logs from DB as `{"type":"log",...}`,  
(3) if already done/failed send `{"type":"done","status":...}` and close,  
(4) loop await `asyncio.wait_for(JOB_QUEUES[job_id].get(), timeout=1.0)`, catch `TimeoutError` to recheck status, catch `WebSocketDisconnect` to close silently.

---

## Non-negotiable rules

1. Accept connection only if job exists.
2. Use per-job queue: `JOB_QUEUES[job_id]` (not global).
3. Replay full log history ordered by timestamp ASC.
4. Log message format:
   ```json
   {"type": "log", "message": str, "timestamp": str}
   ```
5. Terminal message format:
   ```json
   {"type": "done", "status": "done"}
   {"type": "done", "status": "failed"}
   ```
6. Valid job statuses are exactly:
   - `pending`
   - `running`
   - `done`
   - `failed`
7. On `WebSocketDisconnect` → silently close.
8. Never change job state from WebSocket layer.
9. Use raw sqlite3 via `get_connection()`.

---

## Required implementation structure

### Step 1 — Validate job exists

- Query `jobs` table by `id`.
- If not found → close connection immediately (or reject before accept).

```python
row = conn.execute(
    "SELECT status FROM jobs WHERE id = ?",
    (job_id,),
).fetchone()

if row is None:
    await websocket.close()
    return
```

---

### Step 2 — Send historical logs

```python
rows = conn.execute(
    """
    SELECT message, timestamp
    FROM logs
    WHERE job_id = ?
    ORDER BY timestamp ASC
    """,
    (job_id,),
).fetchall()

for r in rows:
    await websocket.send_json({
        "type": "log",
        "message": r["message"],
        "timestamp": r["timestamp"],
    })
```

---

### Step 3 — If already terminal, send done and close

If status is `done` or `failed`:

```python
await websocket.send_json({
    "type": "done",
    "status": status,
})
await websocket.close()
return
```

Do not enter queue loop.

---

### Step 4 — Stream live logs

Main loop:

```python
while True:
    try:
        message = await asyncio.wait_for(
            JOB_QUEUES[job_id].get(),
            timeout=1.0,
        )

        await websocket.send_json({
            "type": "log",
            "message": message["message"],
            "timestamp": message["timestamp"],
        })

    except asyncio.TimeoutError:
        # Re-check job status
        status_row = conn.execute(
            "SELECT status FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()

        if status_row["status"] in ("done", "failed"):
            await websocket.send_json({
                "type": "done",
                "status": status_row["status"],
            })
            break

    except WebSocketDisconnect:
        # EC-18: silently close
        break
```

After loop:
```python
await websocket.close()
```

---

## Required queue behavior

- Worker must create:
  ```python
  JOB_QUEUES[job_id] = asyncio.Queue()
  ```
- Worker must remove it in `finally`:
  ```python
  JOB_QUEUES.pop(job_id, None)
  ```
- WebSocket must tolerate missing queue after terminal state.

---

## Prohibited patterns

- ❌ Streaming logs without sending history first
- ❌ Blocking on `queue.get()` without timeout
- ❌ Infinite await without status re-check
- ❌ Interrupting worker on disconnect
- ❌ Using global shared queue
- ❌ Sending status names outside allowed 4
- ❌ Modifying DB state inside WebSocket handler
- ❌ Using ORM

---

## Definition of done

- Job existence validated before streaming
- Full historical logs replayed in ASC order
- Live logs streamed from `JOB_QUEUES[job_id]`
- `asyncio.wait_for(..., timeout=1.0)` used
- Timeout triggers status re-check
- Terminal message sent exactly once
- WebSocketDisconnect handled silently
- No worker interruption
```