```markdown
---
name: entrypoint-bash-ampersand-wait-trap
description: Implements entrypoint.sh using bash with background processes (&), PID tracking, SIGTERM/SIGINT trap, and wait -n to terminate when either backend or frontend exits. Use when editing entrypoint.sh in DevOps / Docker.
---
# entrypoint-bash-ampersand-wait-trap

## When to use
Use this skill when working on:

- `entrypoint.sh`
- Container startup logic
- Process lifecycle management
- Signal handling in Docker
- Backend + frontend orchestration

Applies only to **AI Landing Page Uniqueizer** infrastructure.

---

## Rationale from PRD

§7.2:

- `entrypoint.sh` must:
  - Launch backend (`uvicorn`)
  - Launch frontend (`next start`)
  - Use `&` to background both
  - Store both PIDs
  - Handle `SIGTERM` and `SIGINT`
  - Kill both processes on signal
  - Use `wait -n`
  - Exit when either process dies
- No `supervisord`
- No external process manager

---

## Required instruction

In `entrypoint.sh`:

- Launch:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
```

- Launch (from frontend dir):

```bash
npm run start -- --port 3000 --hostname 0.0.0.0 &
```

- Store PIDs
- Add:

```bash
trap "kill $BACKEND_PID $FRONTEND_PID" SIGTERM SIGINT
```

- Use:

```bash
wait -n $BACKEND_PID $FRONTEND_PID
```

- On any exit:
  - kill both
  - exit with captured code

---

## Non-negotiable rules

1. Must use `bash`.
2. Must use background `&`.
3. Must store PIDs explicitly.
4. Must implement `trap`.
5. Must use `wait -n`.
6. Must kill both processes if one exits.
7. Must propagate exit code.
8. Must not use supervisord.
9. Must not use pm2.
10. Must not use `&&` chaining.
11. Must not block on single `wait`.

---

# Required entrypoint.sh implementation

```bash
#!/usr/bin/env bash

set -e

# Start backend
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Start frontend
cd /app/frontend
npm run start -- --port 3000 --hostname 0.0.0.0 &
FRONTEND_PID=$!

# Signal handler
trap "echo '[entrypoint] Shutting down...'; kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" SIGTERM SIGINT

# Wait for either process to exit
wait -n $BACKEND_PID $FRONTEND_PID
EXIT_CODE=$?

# If one exits, kill the other
kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true

# Wait for both to terminate
wait $BACKEND_PID 2>/dev/null || true
wait $FRONTEND_PID 2>/dev/null || true

exit $EXIT_CODE
```

---

# Required behavior

## Startup

- Backend runs in background
- Frontend runs in background
- Both PIDs captured

## Signal handling

If container receives:

- `SIGTERM`
- `SIGINT`

Then:

- Both processes must be killed
- Script exits cleanly

## Crash handling

If:

- Backend crashes
OR
- Frontend crashes

Then:

- `wait -n` returns
- Other process killed
- Container exits with failing exit code

---

# Correct execution flow

1. Start backend
2. Capture `$BACKEND_PID`
3. Start frontend
4. Capture `$FRONTEND_PID`
5. Register trap
6. `wait -n`
7. Kill remaining process
8. Exit with captured code

---

# Prohibited patterns

- ❌ Using supervisord
- ❌ Using pm2
- ❌ Using `wait` without `-n`
- ❌ Not capturing PIDs
- ❌ Ignoring signals
- ❌ Using infinite sleep
- ❌ Running processes in foreground sequentially
- ❌ Using Docker CMD with multiple commands
- ❌ Using `exec` incorrectly for both processes

---

# Definition of done

- Backend and frontend started via `&`
- PIDs stored in variables
- `trap` handles SIGTERM and SIGINT
- `wait -n` used correctly
- If one process dies, the other is killed
- Exit code propagated
- No supervisord
- Fully compliant with PRD §7.2
```