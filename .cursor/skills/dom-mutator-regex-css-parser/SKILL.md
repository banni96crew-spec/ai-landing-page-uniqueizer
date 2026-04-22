---
name: dom-mutator-regex-css-parser
description: Implements build_selector_map() using dual-source selector extraction (HTML attributes as primary, regex-based CSS parsing as secondary) without cssutils, generating alias map with hex-based bare names and exclusion prefix filtering. Use when editing backend/worker/module_dom_mutator.py in Backend / Worker.
---
# dom-mutator-regex-css-parser

## When to use
Use this skill when working on:

- `backend/worker/module_dom_mutator.py`
- `build_selector_map()`
- HTML attribute + CSS selector extraction logic
- M3.1 / M3.2 implementation
- Class/ID alias mapping

Applies only to **AI Landing Page Uniqueizer** worker.

---

## Rationale from PRD

§3.3 Module 2 (DOM Mutator):

- **Two sources** must be merged and deduplicated:
  - **Primary:** `class=""` and `id=""` attributes extracted from `index.html` via BeautifulSoup.
  - **Secondary:** selectors extracted from CSS files via regex only.
- CSS regex pattern (exact):

```python
re.compile(r'(?<!["\'])([.#][\w-]+)(?=\s*[{,:\[])')
```

- Alias format: `'x' + 4 hex chars`, stored as **bare name** (without `.` / `#` prefix).
  Example:
  ```
  "order-btn"   → "x8f9q"
  "main-section" → "x1a2b"
  ```
- Do NOT use `cssutils`.
- Respect `exclusion_prefixes: tuple[str, ...]` — already parsed by the caller.
- EC-06:
  - On file read/parse error → log warn:
    ```
    "CSS parse failed: {filename}"
    ```
  - Skip that file, continue pipeline.

---

## Required instruction

In `build_selector_map(html_file, css_files, exclusion_prefixes)`:

1. **Primary pass** — parse `html_file` with BeautifulSoup, collect all `class` values and `id` values as bare strings into a `set`.
2. **Secondary pass** — for each CSS file, apply the regex via `finditer`, strip `.`/`#` prefix, add bare name to the same `set`. Wrap each file in `try/except`; on failure log warn and `continue`.
3. **Alias generation** — iterate the deduplicated set, skip names matching any `exclusion_prefixes` entry, assign `'x' + hex(random.randint(0, 0xFFFF))[2:].zfill(4)` per unique bare name.
4. **Return** `dict[bare_name, bare_alias]`.

---

## Non-negotiable rules

1. HTML attributes (`class`, `id`) are the **primary** source and must be processed before CSS files.
2. CSS extraction uses regex only — never `cssutils` or any AST parser.
3. Must support both `.class` and `#id` from CSS; and multi-class HTML attributes.
4. Selector map keys and values are **bare names** — no `.` or `#` prefix.
5. Alias format exactly: `'x' + 4 hex chars` (total length 5 chars).
6. `exclusion_prefixes` arrives as `tuple[str, ...]` — do not re-parse from string inside this function.
7. On CSS file read/parse error → log warn + skip file. Do not crash worker.
8. Must not mutate any file during selector extraction phase.
9. One alias per unique bare name — no duplicates, no regeneration for already-mapped names.

---

# Required implementation structure

## Function signature

```python
def build_selector_map(
    html_file: Path,
    css_files: list[Path],
    exclusion_prefixes: tuple[str, ...],
) -> dict[str, str]:
```

Returns mapping of **bare names**:

```python
{
    "order-btn":   "x8f9q",
    "main-section": "x1a2b",
}
```

---

## Step 1 — Primary source: HTML attributes

```python
from bs4 import BeautifulSoup

selectors: set[str] = set()

soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "lxml")
for tag in soup.find_all(True):
    for cls in tag.get("class", []):
        selectors.add(cls)          # bare class name, e.g. "order-btn"
    if tag_id := tag.get("id"):
        selectors.add(tag_id)       # bare id name, e.g. "main-section"
```

- `tag.get("class", [])` already returns a list of bare class tokens (BeautifulSoup splits by whitespace).
- `tag.get("id")` returns a bare id string.
- No stripping needed — values are already bare.

---

## Step 2 — Secondary source: CSS files (regex)

Must use exactly:

```python
css_pattern = re.compile(r'(?<!["\'])([.#][\w-]+)(?=\s*[{,:\[])')
```

Per-file processing:

```python
for css_file in css_files:
    try:
        css_text = css_file.read_text(encoding="utf-8", errors="replace")
        for match in css_pattern.finditer(css_text):
            selectors.add(match.group(1).lstrip('.#'))  # strip prefix → bare name
    except Exception:
        log_warn(job_id, f"CSS parse failed: {css_file.name}")
        continue
```

On failure:
- Log exactly: `CSS parse failed: {filename}`
- Skip file.
- Do not stop the pipeline.

---

## Step 3 — Alias generation

```python
import random

selector_map: dict[str, str] = {}
for sel in selectors:
    if any(sel.startswith(p) for p in exclusion_prefixes):
        continue
    alias = 'x' + hex(random.randint(0, 0xFFFF))[2:].zfill(4)
    selector_map[sel] = alias
return selector_map
```

- `random.randint(0, 0xFFFF)` + `zfill(4)` guarantees exactly 4 hex chars.
- Always prefix result with `"x"` → total alias length = 5 chars.
- `exclusion_prefixes` is already a `tuple[str, ...]` — iterate directly.

---

## Exclusion prefix filtering

`exclusion_prefixes` is passed in as a pre-parsed tuple, e.g.:

```python
("js-", "swiper-")
```

Parsing from the settings string (`"js-,swiper-"`) is the **caller's responsibility** — done outside `build_selector_map`. Inside the function, use the tuple directly:

```python
if any(sel.startswith(p) for p in exclusion_prefixes):
    continue
```

Examples:

```
"order-btn"  → process   ✅
"js-toggle"  → skip      ❌ (matches "js-")
"swiper-item"→ skip      ❌ (matches "swiper-")
```

---

## Map building rules

- One alias per unique bare name.
- Do not regenerate alias for an already-mapped name.
- If a name appears in both HTML and CSS sources — deduplicated by the `set`, one alias assigned.
- Alias collisions are extremely unlikely (random 16-bit space) but acceptable.

---

# Correct output shape

## Input

`index.html` fragment:
```html
<div class="order-btn js-toggle">...</div>
<section id="main-section">...</section>
```

`styles.css`:
```css
.order-btn    { color: red; }
#main-section { padding: 10px; }
.js-toggle    { display: none; }
.swiper-item  { overflow: hidden; }
```

`exclusion_prefixes = ("js-", "swiper-")`

## Output map

```python
{
    "order-btn":    "x8f9q",
    "main-section": "x1a2b",
}
```

`"js-toggle"` and `"swiper-item"` excluded.
`"order-btn"` and `"main-section"` deduplicated across both sources.

---

# Prohibited patterns

- ❌ Using `cssutils`
- ❌ Parsing CSS via AST
- ❌ Using non-regex selector extraction
- ❌ Skipping the primary HTML attribute pass
- ❌ Storing `.class` or `#id` prefixes in map keys or values
- ❌ Accepting `js_class_exclusion_prefixes` as raw string and splitting inside this function
- ❌ Failing entire module on one bad CSS file
- ❌ Ignoring exclusion prefixes
- ❌ Generating alias without `'x'` prefix
- ❌ Generating alias with fewer or more than 4 hex chars
- ❌ Replacing selectors during the extraction phase

---

# Definition of done

- `html_file` parsed with BeautifulSoup as primary source ✅
- CSS files processed with exact regex pattern as secondary source ✅
- Results from both sources merged and deduplicated ✅
- `cssutils` not imported ✅
- Map keys and values are bare names (no `.` / `#` prefix) ✅
- Alias format: `'x' + 4 hex chars` ✅
- `exclusion_prefixes` received as `tuple[str, ...]`, not re-parsed ✅
- EC-06 implemented: log warn + skip file on CSS read/parse error ✅
- No worker crash ✅
- Selector map built correctly for all sources ✅
