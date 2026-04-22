```markdown
---
name: nextjs-app-router-react-context-reducer
description: Enforces Next.js App Router architecture with React Context + useReducer state management, native fetch API usage, and proper notFound() handling. Use when editing frontend app directory, context providers, API calls, or routing logic in Frontend / Next.js.
---
# nextjs-app-router-react-context-reducer

## When to use
Use this skill when working on:

- `frontend/app/` directory
- App Router pages and layouts
- Jobs state management
- Context providers
- API integration
- `app/jobs/[id]/page.tsx`
- `app/not-found.tsx`

Applies only to **AI Landing Page Uniqueizer** frontend.

---

## Rationale from PRD

§5.2, §5.4:

- Must use **Next.js App Router**
- Must NOT use Pages Router
- State management via:
  - React Context
  - `useReducer`
- Actions:
  - `ADD_JOB`
  - `UPDATE_JOB_STATUS`
  - `SET_JOBS`
  - `DELETE_JOB`
- Use **native fetch**
- On 404 in `app/jobs/[id]/page.tsx`:
  - Call `notFound()` from `next/navigation`
  - Render `app/not-found.tsx`
- Never use axios
- Never use `pages/` directory

---

## Required instruction

- Use Next.js App Router exclusively.
- Create `JobsContext` with `useReducer` for `{jobs, currentJob, dispatch}`.
- Define action types:
  - `ADD_JOB`
  - `UPDATE_JOB_STATUS`
  - `SET_JOBS`
  - `DELETE_JOB`
- Use native `fetch()` for all API calls.
- In `app/jobs/[id]/page.tsx`:
  - On 404 from API → `notFound()`
- Never use `pages/` directory.
- Never use axios.

---

## Non-negotiable rules

1. Use `app/` directory structure.
2. Never create `pages/`.
3. Use React 18.
4. Use `useReducer` (not Redux/Zustand/etc).
5. Use native `fetch`.
6. Use environment variable:
   ```
   NEXT_PUBLIC_API_URL
   ```
7. On 404 → call `notFound()` immediately.
8. `not-found.tsx` must exist under `app/`.
9. No axios import anywhere.
10. No external state management libraries.

---

# Required directory structure

```
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx
│   ├── dashboard/page.tsx
│   ├── jobs/[id]/page.tsx
│   ├── settings/page.tsx
│   └── not-found.tsx
└── components/
```

Never introduce `pages/`.

---

# JobsContext implementation

## Context shape

```ts
type Job = {
  id: number
  status: 'pending' | 'running' | 'done' | 'failed'
  target_url: string
}

type JobsState = {
  jobs: Job[]
  currentJob: Job | null
}
```

---

## Action types (exact)

```ts
type Action =
  | { type: 'ADD_JOB'; payload: Job }
  | { type: 'UPDATE_JOB_STATUS'; payload: { id: number; status: Job['status'] } }
  | { type: 'SET_JOBS'; payload: Job[] }
  | { type: 'DELETE_JOB'; payload: number }
```

No additional action types allowed.

---

## Reducer

```ts
function jobsReducer(state: JobsState, action: Action): JobsState {
  switch (action.type) {
    case 'ADD_JOB':
      return {
        ...state,
        jobs: [action.payload, ...state.jobs],
      }

    case 'UPDATE_JOB_STATUS':
      return {
        ...state,
        jobs: state.jobs.map(job =>
          job.id === action.payload.id
            ? { ...job, status: action.payload.status }
            : job
        ),
      }

    case 'SET_JOBS':
      return {
        ...state,
        jobs: action.payload,
      }

    case 'DELETE_JOB':
      return {
        ...state,
        jobs: state.jobs.filter(job => job.id !== action.payload),
      }

    default:
      return state
  }
}
```

---

## Context provider

```ts
'use client'

import { createContext, useReducer, ReactNode } from 'react'

export const JobsContext = createContext<{
  state: JobsState
  dispatch: React.Dispatch<Action>
} | null>(null)

export function JobsProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(jobsReducer, {
    jobs: [],
    currentJob: null,
  })

  return (
    <JobsContext.Provider value={{ state, dispatch }}>
      {children}
    </JobsContext.Provider>
  )
}
```

Wrap provider in `app/layout.tsx`.

---

# Native fetch usage (mandatory)

All API calls must use:

```ts
await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/jobs`)
```

Never:

- `axios`
- `fetch wrapper libraries`
- `SWR`
- `React Query`

Example:

```ts
const res = await fetch(`${API_URL}/api/jobs/${id}`)

if (!res.ok) {
  if (res.status === 404) {
    notFound()
  }
  throw new Error(`Error ${res.status}`)
}
```

---

# 404 handling in app/jobs/[id]/page.tsx

Must import:

```ts
import { notFound } from 'next/navigation'
```

If API returns 404:

```ts
if (res.status === 404) {
  notFound()
}
```

This must render:

```
app/not-found.tsx
```

Do not manually redirect.

---

# not-found.tsx

Location:

```
app/not-found.tsx
```

Must use `notFound()` mechanism from App Router.
Do not implement custom 404 route manually.

---

# Prohibited patterns

- ❌ Creating `pages/` directory
- ❌ Using Pages Router
- ❌ Using axios
- ❌ Using Redux
- ❌ Using Zustand
- ❌ Using SWR/React Query
- ❌ Manual 404 redirects
- ❌ Using `window.location`
- ❌ Global state outside Context
- ❌ Class components

---

# Definition of done

- App Router only
- `JobsContext` implemented with `useReducer`
- Action types exactly:
  - ADD_JOB
  - UPDATE_JOB_STATUS
  - SET_JOBS
  - DELETE_JOB
- All API calls use native `fetch`
- `app/jobs/[id]/page.tsx` calls `notFound()` on 404
- `app/not-found.tsx` exists
- No axios import anywhere
- No `pages/` directory present
- State managed exclusively via React Context + useReducer
```