```markdown
---
name: job-status-badge-four-state-mapping
description: Enforces strict four-state JobStatusBadge mapping (pending, running, done, failed) with exact STATUS_CONFIG and Tailwind opacity syntax using /10. Use when editing frontend/components/JobStatusBadge.tsx in Frontend / Next.js.
---
# job-status-badge-four-state-mapping

## When to use
Use this skill when working on:

- `frontend/components/JobStatusBadge.tsx`
- Job status UI rendering
- Status label/color mapping
- Status-related styling logic

Applies only to **AI Landing Page Uniqueizer** frontend.

---

## Rationale from PRD

§5.3 FIX v1.1:

- Exactly 4 valid statuses:
  - `pending`
  - `running`
  - `done`
  - `failed`
- No other status allowed.
- Must define `STATUS_CONFIG` with:
  - `label`
  - `color`
- Tailwind background opacity must use `/10` syntax:
  - `bg-warn/10`
  - `bg-success/10`
  - `bg-error/10`

---

## Required instruction

In `JobStatusBadge.tsx`, define `STATUS_CONFIG` with exactly 4 keys:

```ts
pending → { label:'Queued', color:'text-text-secondary bg-border' }

running → { label:'Processing', color:'text-warn bg-warn/10' }

done → { label:'Done', color:'text-success bg-success/10' }

failed → { label:'Failed', color:'text-error bg-error/10' }
```

Apply:

```tsx
className="px-2 py-1 rounded-md text-xs font-medium"
```

Never add a `"completed"` status.

---

## Non-negotiable rules

1. Only 4 statuses supported.
2. Must not add `completed`.
3. Must not add intermediate states.
4. Must not map unknown statuses silently.
5. Must use semantic design tokens (no hex).
6. Must use `/10` opacity syntax.
7. Must use exact class base:
   ```
   px-2 py-1 rounded-md text-xs font-medium
   ```

---

# Required implementation

## STATUS_CONFIG (exact)

```ts
const STATUS_CONFIG = {
  pending: {
    label: 'Queued',
    color: 'text-text-secondary bg-border',
  },
  running: {
    label: 'Processing',
    color: 'text-warn bg-warn/10',
  },
  done: {
    label: 'Done',
    color: 'text-success bg-success/10',
  },
  failed: {
    label: 'Failed',
    color: 'text-error bg-error/10',
  },
} as const
```

Must not add additional keys.

---

## Component shape

```tsx
type JobStatus = 'pending' | 'running' | 'done' | 'failed'

export function JobStatusBadge({ status }: { status: JobStatus }) {
  const config = STATUS_CONFIG[status]

  return (
    <span
      className={`px-2 py-1 rounded-md text-xs font-medium ${config.color}`}
    >
      {config.label}
    </span>
  )
}
```

---

# Required mapping behavior

| Status   | Label       | Classes |
|----------|------------|---------|
| pending  | Queued     | `text-text-secondary bg-border` |
| running  | Processing | `text-warn bg-warn/10` |
| done     | Done       | `text-success bg-success/10` |
| failed   | Failed     | `text-error bg-error/10` |

---

# Tailwind opacity rule

Must use:

```
bg-warn/10
bg-success/10
bg-error/10
```

Must NOT use:

```
bg-warn bg-opacity-10
```

---

# Prohibited patterns

- ❌ Adding `completed`
- ❌ Adding `processing`
- ❌ Using uppercase statuses
- ❌ Using hex colors
- ❌ Using Tailwind default colors
- ❌ Using inline styles
- ❌ Missing one of the 4 statuses
- ❌ Changing label text
- ❌ Different base padding/font classes

---

# Definition of done

- STATUS_CONFIG has exactly 4 keys
- No `completed` status exists
- Exact label text used
- Correct color tokens used
- `/10` opacity syntax used
- Base class `px-2 py-1 rounded-md text-xs font-medium` applied
- Type-safe status union enforced
- Fully compliant with PRD §5.3 FIX v1.1
```