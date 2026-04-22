```markdown
---
name: progressbar-framer-motion-stage-label
description: Implements ProgressBar.tsx using framer-motion with animated width, separate STATUS_LABELS mapping, and stage label displayed under the bar. Use when editing frontend/components/ProgressBar.tsx in Frontend / Next.js.
---
# progressbar-framer-motion-stage-label

## When to use
Use this skill when working on:

- `frontend/components/ProgressBar.tsx`
- Progress animation logic
- Job stage display
- framer-motion integration
- Status-to-label mapping for progress

Applies only to **AI Landing Page Uniqueizer** frontend.

---

## Rationale from PRD

§5.3:

- Use `framer-motion`
- Animate width:
  ```tsx
  animate={{ width: `${progress_pct}%` }}
  ```
- Transition:
  ```tsx
  transition={{ duration: 0.8, ease: "easeInOut" }}
  ```
- `STATUS_LABELS` must be defined in this file
- Must be separate from `STATUS_CONFIG` in `JobStatusBadge`
- Show stage label under bar

---

## Required instruction

In `ProgressBar.tsx`:

- Outer div:
  ```tsx
  className="h-1 bg-border rounded-full overflow-hidden"
  ```
- Inner `motion.div`:
  ```tsx
  animate={{width:`${progress_pct}%`}}
  transition={{duration:0.8,ease:"easeInOut"}}
  className="h-full bg-accent rounded-full"
  ```
- Below bar:
  ```tsx
  <p className="text-xs text-text-secondary mt-2">
    Stage: {STATUS_LABELS[status]} ({progress_pct}%)
  </p>
  ```
- Define `STATUS_LABELS` in same file.
- Must be separate from `STATUS_CONFIG`.

---

## Non-negotiable rules

1. Must use `framer-motion`.
2. Must use `motion.div`.
3. Must animate width via `progress_pct`.
4. Transition must match:
   - `duration: 0.8`
   - `ease: "easeInOut"`
5. Must use semantic design tokens.
6. Must define `STATUS_LABELS` locally.
7. Must not import `STATUS_CONFIG`.
8. Must show stage label under bar.
9. Must show progress percentage in text.
10. Must not use CSS animation instead of framer-motion.

---

# Required implementation

## STATUS_LABELS (exact mapping)

```ts
const STATUS_LABELS: Record<JobStatus, string> = {
  pending: 'Waiting in queue',
  running: 'Processing...',
  done: 'Completed',
  failed: 'Failed',
}
```

Must match exactly.

Must not reuse labels from JobStatusBadge.

---

## Component structure

```tsx
'use client'

import { motion } from 'framer-motion'

type JobStatus = 'pending' | 'running' | 'done' | 'failed'

interface Props {
  status: JobStatus
  progress_pct: number
}

export function ProgressBar({ status, progress_pct }: Props) {
  return (
    <div>
      <div className="h-1 bg-border rounded-full overflow-hidden">
        <motion.div
          animate={{ width: `${progress_pct}%` }}
          transition={{ duration: 0.8, ease: 'easeInOut' }}
          className="h-full bg-accent rounded-full"
        />
      </div>

      <p className="text-xs text-text-secondary mt-2">
        Stage: {STATUS_LABELS[status]} ({progress_pct}%)
      </p>
    </div>
  )
}
```

---

# Visual requirements

- Bar height: `h-1`
- Background: `bg-border`
- Rounded: `rounded-full`
- Inner bar: `bg-accent`
- Stage label:
  - `text-xs`
  - `text-text-secondary`
  - `mt-2`

---

# Separation of concerns

- `JobStatusBadge` → handles visual status badge.
- `ProgressBar` → handles stage + percentage.
- `STATUS_LABELS` must not be imported from badge component.
- Both mappings intentionally separate.

---

# Prohibited patterns

- ❌ Using CSS transitions instead of framer-motion
- ❌ Missing transition config
- ❌ Not animating width
- ❌ Using inline style width instead of animate
- ❌ Reusing STATUS_CONFIG
- ❌ Hardcoding hex colors
- ❌ Using Tailwind default colors
- ❌ Placing label above bar
- ❌ Omitting percentage display

---

# Definition of done

- `motion.div` used
- `animate={{width:\`\${progress_pct}%\`}}`
- `transition={{duration:0.8,ease:"easeInOut"}}`
- Outer container uses exact class string
- Inner bar uses exact class string
- Stage label rendered under bar
- `STATUS_LABELS` defined locally
- Label text matches PRD
- Fully compliant with §5.3
```