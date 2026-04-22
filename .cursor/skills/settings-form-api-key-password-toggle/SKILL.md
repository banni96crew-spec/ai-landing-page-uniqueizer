```markdown
---
name: settings-form-api-key-password-toggle
description: Implements SettingsForm.tsx with isDirty tracking, password toggle for _api_key fields, conditional Save button state, and success toast with 2000ms timeout. Use when editing frontend/components/SettingsForm.tsx in Frontend / Next.js.
---
# settings-form-api-key-password-toggle

## When to use
Use this skill when working on:

- `frontend/components/SettingsForm.tsx`
- Settings UI logic
- API key fields rendering
- Save button behavior
- PUT `/api/settings` integration
- Toast feedback logic

Applies only to **AI Landing Page Uniqueizer** frontend.

---

## Rationale from PRD

§5.3:

- Track `isDirty` state
- Save button active only when dirty
- `_api_key` fields:
  - `type="password"`
  - Show/Hide toggle
- On successful save:
  - Show toast `"Settings saved"`
  - Hide after 2000ms
- PUT body must be:
  ```ts
  Object.entries(settings).map(([key,value])=>({key,value}))
  ```

---

## Required instruction

In `SettingsForm.tsx`:

- Track `isDirty: boolean`
- Detect `'_api_key' in key`
  - Render password input
  - Add show/hide toggle button
- Save button:
  ```tsx
  disabled={!isDirty || isSaving}
  ```
- On success:
  ```ts
  setSuccessMsg('Settings saved')
  setTimeout(()=>setSuccessMsg(null), 2000)
  ```
- PUT body:
  ```ts
  Object.entries(settings).map(([key,value])=>({key,value}))
  ```

---

## Non-negotiable rules

1. Use native `fetch`.
2. Must track `isDirty`.
3. Must track `isSaving`.
4. Must disable Save if not dirty.
5. Must disable Save while saving.
6. Must use `type="password"` for `_api_key`.
7. Must provide show/hide toggle.
8. Must show toast exactly `"Settings saved"`.
9. Must hide toast after 2000ms.
10. Must send array payload `{key,value}`.
11. Must not use axios.
12. Must not auto-save.

---

# Required implementation structure

## State

```ts
const [settings, setSettings] = useState<Record<string, string>>({})
const [initialSettings, setInitialSettings] = useState<Record<string, string>>({})
const [isDirty, setIsDirty] = useState(false)
const [isSaving, setIsSaving] = useState(false)
const [successMsg, setSuccessMsg] = useState<string | null>(null)
```

---

## Dirty detection

```ts
useEffect(() => {
  const dirty =
    JSON.stringify(settings) !== JSON.stringify(initialSettings)

  setIsDirty(dirty)
}, [settings, initialSettings])
```

Must update when values change.

---

## API key field rendering

When rendering inputs:

```ts
Object.entries(settings).map(([key, value]) => {
  const isApiKey = key.includes('_api_key')
```

If `isApiKey`:

```tsx
<div className="relative">
  <input
    type={showMap[key] ? 'text' : 'password'}
    value={value}
    onChange={...}
    className="..."
  />
  <button
    type="button"
    onClick={() => toggleVisibility(key)}
    className="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-accent"
  >
    {showMap[key] ? 'Hide' : 'Show'}
  </button>
</div>
```

Must:

- Use `type="password"` default.
- Toggle between `text` and `password`.

---

## Save button

```tsx
<button
  type="submit"
  disabled={!isDirty || isSaving}
  className="bg-accent hover:bg-accent-hover text-text-primary px-4 py-2 rounded-md disabled:opacity-50"
>
  {isSaving ? 'Saving...' : 'Save'}
</button>
```

Must use:

```
disabled={!isDirty || isSaving}
```

---

## Submit handler

```ts
const handleSubmit = async (e: React.FormEvent) => {
  e.preventDefault()
  setIsSaving(true)

  try {
    const res = await fetch(`${API_URL}/api/settings`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(
        Object.entries(settings).map(([key, value]) => ({
          key,
          value,
        }))
      ),
    })

    if (!res.ok) {
      throw new Error(`Error ${res.status}`)
    }

    setInitialSettings(settings)
    setSuccessMsg('Settings saved')

    setTimeout(() => setSuccessMsg(null), 2000)
  } finally {
    setIsSaving(false)
  }
}
```

Must:

- Send array of `{key, value}`
- Not send object directly
- Use native fetch

---

# Toast message

Render conditionally:

```tsx
{successMsg && (
  <div className="text-success text-sm mt-2">
    {successMsg}
  </div>
)}
```

Must disappear after 2000ms.

---

# Prohibited patterns

- ❌ Using axios
- ❌ Using uncontrolled inputs
- ❌ Auto-saving on change
- ❌ Enabling Save when not dirty
- ❌ Using text input for API keys by default
- ❌ Persisting success toast indefinitely
- ❌ Sending object instead of array payload
- ❌ Using hex colors
- ❌ Using default Tailwind palette

---

# Definition of done

- `_api_key` inputs rendered as password
- Show/Hide toggle implemented
- `isDirty` correctly tracks changes
- Save disabled when not dirty
- Save disabled while saving
- PUT body formatted as array of `{key,value}`
- Success toast shows `"Settings saved"`
- Toast auto-hides after 2000ms
- Uses native fetch
- Fully compliant with PRD §5.3
```