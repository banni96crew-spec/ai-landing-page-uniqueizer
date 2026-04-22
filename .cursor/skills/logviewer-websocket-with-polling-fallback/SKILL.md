```markdown
---
name: logviewer-websocket-with-polling-fallback
description: Implements LogViewer.tsx with WebSocket streaming from NEXT_PUBLIC_WS_URL, auto-scroll behavior, Skeleton loading state, and polling fallback every 3000ms when WS is closed and job not terminal. Use when editing frontend/components/LogViewer.tsx in Frontend / Next.js.
---
# logviewer-websocket-with-polling-fallback

## When to use
Use this skill when working on:

- `frontend/components/LogViewer.tsx`
- WebSocket log streaming
- Job progress UI
- Polling fallback logic
- Auto-scroll behavior
- Skeleton loading state

Applies only to **AI Landing Page Uniqueizer** frontend.

---

## Rationale from PRD

§5.3, §5.4:

- WebSocket URL from:
  ```
  NEXT_PUBLIC_WS_URL
  ```
- Endpoint:
  ```
  /ws/logs/{jobId}
  ```
- `data.type === "done"`:
  - `setWsStatus('closed')`
  - Read `data.status`
  - Close WebSocket
- `data.type === "log"`:
  - Append to logs array
- Auto-scroll using `useRef`
- Show `<SkeletonCard />` while `wsStatus === 'connecting'`
- Polling fallback:
  - `useInterval(fetchJob, 3000)`
  - Only when WS closed
  - Only if job not `done` or `failed`

---

## Required instruction

In `LogViewer.tsx`:

- Connect to:
  ```ts
  ${process.env.NEXT_PUBLIC_WS_URL}/ws/logs/${jobId}
  ```
- Handle:
  - `data.type === 'done'`
  - `data.type === 'log'`
- Auto-scroll:
  ```ts
  containerRef.current.scrollTop = containerRef.current.scrollHeight
  ```
- Show `<SkeletonCard lines={5} />` when `wsStatus === 'connecting'`
- Add polling fallback:
  ```ts
  useInterval(fetchJob, 3000)
  ```
  when WS closed.

---

## Non-negotiable rules

1. Must use native WebSocket API.
2. Must use `NEXT_PUBLIC_WS_URL`.
3. Must not use socket.io.
4. Must not use external WS libraries.
5. Must not use axios.
6. Must auto-scroll on each new log.
7. Must close WS on `"done"`.
8. Must implement polling fallback.
9. Poll only when WS is closed AND job not terminal.
10. Must show Skeleton while connecting.
11. Must render log level colors: info→text-accent, warn→text-warn, error→text-error.
12. Must store logs as LogEntry[] (message, timestamp, level), not string[].

---

# Required component structure

## State

```ts
const [logs, setLogs] = useState<string[]>([])
const [wsStatus, setWsStatus] =
  useState<'connecting' | 'connected' | 'closed'>('connecting')
```

---

## WebSocket connection

```ts
useEffect(() => {
  const ws = new WebSocket(
    `${process.env.NEXT_PUBLIC_WS_URL}/ws/logs/${jobId}`
  )

  ws.onopen = () => {
    setWsStatus('connected')
  }

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data)

    if (data.type === 'log') {
  setLogs(prev => [...prev, {
    message: data.message,
    timestamp: data.timestamp,
    level: data.level ?? 'info'
  }])
}

    if (data.type === 'done') {
      setWsStatus('closed')
      // read data.status if needed for UI
      ws.close()
    }
  }

  ws.onclose = () => {
    setWsStatus('closed')
  }

  return () => {
    ws.close()
  }
}, [jobId])
```

Must:

- Parse JSON
- Branch on `data.type`
- Close WS on `"done"`

---

# Auto-scroll (mandatory)

```ts
const containerRef = useRef<HTMLDivElement>(null)

useEffect(() => {
  if (containerRef.current) {
    containerRef.current.scrollTop =
      containerRef.current.scrollHeight
  }
}, [logs])
```

Must trigger on every new log.

---

# Skeleton loading state

When:

```ts
wsStatus === 'connecting'
```

Render:

```tsx
<SkeletonCard lines={5} />
```

Do not render empty state.

---

# Log level color mapping
// Маппинг level → Tailwind-класс цвета (PRD §5.3)
const LOG_LEVEL_COLOR: Record<string, string> = {
  info:  'text-accent',
  warn:  'text-warn',
  error: 'text-error',
}

// Render each log line:
{logs.map((log, i) => (
  <div key={i} className="py-0.5">
    <span className={LOG_LEVEL_COLOR[log.level] ?? 'text-accent'}>
      {log.timestamp}
    </span>
    {' '}
    <span className="text-text-secondary hover:text-text-primary transition-colors">
      {log.message}
    </span>
  </div>
))}

# Polling fallback

## Rule

Polling must activate only when:

- `wsStatus === 'closed'`
- Job status not `'done'`
- Job status not `'failed'`

## Implementation

```ts
useInterval(() => {
  if (
    wsStatus === 'closed' &&
    job.status !== 'done' &&
    job.status !== 'failed'
  ) {
    fetchJob(jobId)
  }
}, 3000)
```

- Interval must be 3000ms.
- Must use `fetchJob` from native fetch.
- Must not poll while WS connected.

---

# Message format handling

Incoming message shapes:

```json
{"type":"log","message":"...","timestamp":"...","level":"info"}
{"type":"log","message":"...","timestamp":"...","level":"warn"}
{"type":"log","message":"...","timestamp":"...","level":"error"}
```

```json
{"type":"done","status":"done"}
```

```json
{"type":"done","status":"failed"}
```

Must handle both `"done"` and `"failed"`.

---

# Styling requirements

Log container:

```tsx
<div
  ref={containerRef}
  className="font-mono text-xs text-text-secondary overflow-y-auto"
>
```

Log levels color:

- `info` → `text-accent`
- `warn` → `text-warn`
- `error` → `text-error`

---

# Prohibited patterns

- ❌ Using axios
- ❌ Using socket.io
- ❌ Using third-party WS wrapper
- ❌ Polling while WS connected
- ❌ Not closing WS on `"done"`
- ❌ No auto-scroll
- ❌ Hardcoded WS URL
- ❌ Infinite polling
- ❌ Not handling `"failed"`

---

# Definition of done

- WebSocket connects to correct URL
- `data.type === 'log'` appends logs
- `data.type === 'done'` closes WS
- `wsStatus` updates correctly
- Auto-scroll implemented via `useRef`
- Skeleton shown during connecting
- Polling fallback runs every 3000ms
- Polling disabled when job terminal
- No axios or external WS libraries used
- Fully compliant with PRD §5.3/§5.4
```