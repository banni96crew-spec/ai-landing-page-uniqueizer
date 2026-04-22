```markdown
---
name: rewrite-asset-urls-with-cache
description: Implements rewrite_asset_urls() with httpx.Client (sync), URL normalization, srcset handling, deterministic caching, and filename collision resolution. Use when editing backend/worker/module_scraper.py asset download and rewriting logic in Backend / Worker.
---
# rewrite-asset-urls-with-cache

## When to use
Use this skill when working on:

- `backend/worker/module_scraper.py`
- `rewrite_asset_urls()`
- Asset downloading logic
- URL normalization and rewriting
- src/srcset/href/action processing
- GAP-B / GAP-E implementation

Applies only to **AI Landing Page Uniqueizer** worker.

---

## Rationale from PRD

§3.3, GAP-B/E:

- Use `httpx.Client` (sync).
- Traverse all tags and attributes from `REWRITABLE_ATTRS`.
- Handle `srcset` explicitly.
- Resolve 7 URL types.
- Maintain cache: `dict[str, str]` (`abs_url → filename`).
- Handle filename collisions using `_{n}` suffix.
- EC-05: HTTP != 200 → log warn + keep original URL.

---

## Required instruction

Implement `rewrite_asset_urls(soup, base_url, raw_dir)` using  
`httpx.Client(timeout=30, follow_redirects=True)`.

Use internal `_downloaded: dict[str,str]` cache.

Handle URL types:

- `data:` / `javascript:` / `mailto:` / `tel:` / `#` → skip
- `//` → prepend scheme
- `/` → `urljoin`
- else → `urljoin`

For `srcset`: split by `','`, process each `token[0]`.

On HTTP != 200 or exception: log warn, return original URL.

---

## Non-negotiable rules

1. Use sync `httpx.Client`.
2. `timeout=30`, `follow_redirects=True`.
3. Use `urllib.parse.urljoin` for resolution.
4. Maintain `_downloaded: dict[str, str]`.
5. Do not redownload cached URLs.
6. On HTTP != 200 → log warn, keep original.
7. On exception → log warn, keep original.
8. Do not use external CSS libraries.
9. Rewrite attributes defined in `REWRITABLE_ATTRS`.
10. Must process `srcset`.

---

# Required implementation structure

## Function signature

```python
def rewrite_asset_urls(soup, base_url: str, raw_dir: Path) -> None:
```

- Mutates `soup` in-place.
- Downloads assets into `raw_dir`.

---

## httpx client

```python
import httpx

with httpx.Client(timeout=30, follow_redirects=True) as client:
    ...
```

Must be sync client.

---

## Internal cache

```python
_downloaded: dict[str, str] = {}
```

Key: absolute URL  
Value: saved filename

If `abs_url in _downloaded`:
- reuse filename
- do not redownload

---

# URL resolution rules (7 types)

Given `original_url`:

### 1. Skip types

If starts with:

- `"data:"`
- `"javascript:"`
- `"mailto:"`
- `"tel:"`
- `"#"`

→ return original unchanged.

---

### 2. Protocol-relative (`//`)

```python
if url.startswith("//"):
    abs_url = f"{urlparse(base_url).scheme}:{url}"
```

---

### 3. Root-relative (`/`)

```python
abs_url = urljoin(base_url, url)
```

---

### 4. Relative path

```python
abs_url = urljoin(base_url, url)
```

---

## Asset download logic

```python
try:
    resp = client.get(abs_url)
    if resp.status_code != 200:
        log_warn(job_id, f"Asset download failed: {abs_url}")
        return original_url
except Exception:
    log_warn(job_id, f"Asset download failed: {abs_url}")
    return original_url
```

EC-05:
- HTTP != 200 → warn
- Keep original URL
- Do not fail job

---

## Filename generation

1. Extract basename from URL path.
2. If empty → generate fallback like `asset.bin`.
3. Ensure safe filename.
4. Collision handling:

If filename exists:
```
image.png
image_1.png
image_2.png
```

Increment `_n` suffix until unused.

---

## Cache logic

After successful download:

```python
_downloaded[abs_url] = filename
```

If URL seen again:
- reuse stored filename
- skip HTTP call

---

# Attribute traversal

## REWRITABLE_ATTRS

Must process:

```python
{'src', 'href', 'action', 'data-src', 'data-href'}
```

For each tag in soup:
- For each attribute in `REWRITABLE_ATTRS`
- If attribute present:
  - rewrite value

---

# srcset handling

Example:

```
image1.jpg 1x, image2.jpg 2x
```

Processing:

```python
items = value.split(",")
new_items = []

for item in items:
    parts = item.strip().split()
    url_part = parts[0]
    descriptor = " ".join(parts[1:])  # may be empty

    new_url = process_url(url_part)

    if descriptor:
        new_items.append(f"{new_url} {descriptor}")
    else:
        new_items.append(new_url)

tag["srcset"] = ", ".join(new_items)
```

Important:
- Only rewrite first token (URL).
- Preserve descriptor.

---

# Correct rewrite behavior

After download:

- Replace attribute value with relative path to saved file.
- Use local filename only (not absolute URL).

Example:
```
<img src="assets/logo.png">
```

---

# Prohibited patterns

- ❌ Async httpx client
- ❌ No timeout defined
- ❌ No redirect following
- ❌ Ignoring srcset
- ❌ Redownloading same URL
- ❌ Crashing on 404
- ❌ Failing entire job on asset error
- ❌ Using f-strings for SQL (if logging DB)
- ❌ Ignoring protocol-relative URLs

---

# Definition of done

- httpx.Client sync used with timeout=30
- All REWRITABLE_ATTRS processed
- srcset correctly rewritten
- Cache prevents duplicate downloads
- Filename collisions resolved with _n suffix
- HTTP != 200 logs warn and keeps original
- No worker crash on asset error
- Soup mutated in-place
```