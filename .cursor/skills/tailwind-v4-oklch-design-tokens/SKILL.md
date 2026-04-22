```markdown
---
name: tailwind-v4-oklch-design-tokens
description: Enforces Tailwind CSS v4 @theme design token system using exact OKLCH color values from PRD §5.1. Use when editing globals.css, layout.tsx, or any component styling in Frontend / Next.js.
---
# tailwind-v4-oklch-design-tokens

## When to use
Use this skill when working on:

- `frontend/app/globals.css`
- Tailwind configuration (v4)
- Component styling
- Layout design system
- Theme tokens
- Typography tokens
- Border and radius tokens

Applies only to **AI Landing Page Uniqueizer** frontend.

---

## Rationale from PRD

§5.1:

- Tailwind CSS v4
- Use `@theme { }` directive inside `globals.css`
- All colors defined using `oklch()`
- No hex values in components
- No Tailwind default color names
- Use semantic token classes:
  - `bg-bg-primary`
  - `text-text-secondary`
  - `text-accent`
  - etc.
- Font:
  ```
  --font-sans: 'Inter', system-ui, sans-serif
  ```
- Radius:
  ```
  --radius-card: 0.75rem
  ```

---

## Required instruction

In `globals.css`, define all design tokens inside:

```css
@theme { }
```

using exact `oklch` values from PRD §5.1.

Never use:

- hardcoded hex
- Tailwind default colors (e.g. `text-blue-500`)
- direct color literals in components

Always reference:

- `bg-bg-primary`
- `text-text-secondary`
- `text-accent`
- etc.

Font:

```css
--font-sans: 'Inter', system-ui, sans-serif;
```

Radius:

```css
--radius-card: 0.75rem;
```

---

# Required globals.css structure

```css
@import "tailwindcss";

@theme {
  --color-bg-primary: oklch(14.5% 0.018 264);
  --color-bg-secondary: oklch(20.5% 0.022 264);

  --color-accent: oklch(56.9% 0.196 264);
  --color-accent-hover: oklch(51.9% 0.196 264);

  --color-text-primary: oklch(97.8% 0.004 264);
  --color-text-secondary: oklch(61.5% 0.045 264);

  --color-border: oklch(26% 0.025 264);

  --color-error: oklch(57.7% 0.215 27.3);
  --color-success: oklch(64.5% 0.148 160);
  --color-warn: oklch(76.9% 0.162 70.6);

  --font-sans: 'Inter', system-ui, sans-serif;

  --radius-card: 0.75rem;
}
```

Values must match exactly.

Do not change OKLCH numbers.

---

# Required token usage in components

## ✅ Correct

```tsx
<div className="bg-bg-primary text-text-primary">
```

```tsx
<button className="bg-accent hover:bg-accent-hover text-text-primary">
```

```tsx
<p className="text-text-secondary">
```

```tsx
<div className="border border-border rounded-[var(--radius-card)]">
```

---

## ❌ Forbidden

```tsx
<div className="bg-[#0F172A]">
```

```tsx
<div className="text-blue-500">
```

```tsx
<div className="bg-slate-800">
```

```tsx
<div style={{ color: '#ffffff' }}>
```

---

# Semantic mapping (must use these classes)

| Token | Tailwind class |
|-------|----------------|
| bg-primary | `bg-bg-primary` |
| bg-secondary | `bg-bg-secondary` |
| accent | `text-accent` / `bg-accent` |
| accent-hover | `hover:bg-accent-hover` |
| text-primary | `text-text-primary` |
| text-secondary | `text-text-secondary` |
| border | `border-border` |
| error | `text-error` |
| success | `text-success` |
| warn | `text-warn` |

---

# Typography rules (must match PRD)

Apply via Tailwind classes:

- H1:
  ```
  text-2xl font-semibold text-text-primary tracking-tight
  ```

- H2:
  ```
  text-lg font-medium text-text-primary
  ```

- Body:
  ```
  text-sm text-text-primary leading-relaxed
  ```

- Caption:
  ```
  text-xs text-text-secondary
  ```

- Mono:
  ```
  font-mono text-xs text-text-secondary
  ```

---

# Layout requirement (layout.tsx)

Root layout must include:

```tsx
<body className="bg-bg-primary font-sans">
```

And:

```tsx
<html data-theme="dark">
```

---

# Prohibited patterns

- ❌ Using hex color codes anywhere in components
- ❌ Using Tailwind default palette (blue-500, slate-900, etc.)
- ❌ Inline styles for color
- ❌ Defining tokens outside @theme
- ❌ Using tailwind.config.js for theme extension
- ❌ Adding additional colors not defined in PRD
- ❌ Modifying OKLCH values

---

# Definition of done

- All tokens defined inside `@theme`
- Exact OKLCH values used
- No hex colors in components
- No Tailwind default color utilities used
- All components reference semantic tokens
- Font defined as:
  ```
  'Inter', system-ui, sans-serif
  ```
- Radius defined as:
  ```
  0.75rem
  ```
- Design system strictly centralized in globals.css
```