```markdown
---
name: css-url-rewrite-regex-callback
description: Implements rewrite_css_urls() using re.sub with CSS_URL_PATTERN callback and shared download/cache logic identical to rewrite_asset_urls. Use when editing backend/worker/module_scraper.py CSS processing and asset rewriting in Backend / Worker.
---
# css-url-rewrite-regex-callback

## When to use
Use this skill when working on:

- `backend/worker/module_scraper.py`
- CSS processing logic
- `rewrite_css_urls()`
- GAP-E implementation
- URL rewriting inside CSS files

Applies only to **AI Landing Page Uniqueizer** worker.

---

## Rationale from PRD

§3.3, GAP-E:

- CSS rewriting must use `re.sub` with callback.
- Pattern:

```python
CSS_URL_PATTERN = re.compile(
    r"""url\(\s*(['"]?)([^'"\)]+)\1\s*\)""",
    re.IGNORECASE,
)
```

- Download logic must be identical to `rewrite_asset_urls()`.
- Use `css_file_base_url` for resolving relative paths.

---

## Required instruction

Implement `rewrite_css_urls(css_text, css_file_base_url, assets_dir, cache, client)`.

Use:

```python
CSS_URL_PATTERN.sub(callback, css_text)
```

Callback must:

1. Extract `quote` and `url_value`.
2. Call `_resolve_and_download(url_value, css_file_base_url, urlparse(css_file_base_url).scheme, assets_dir, cache, client)`.
3. Return:

```python
url({quote}{new_url}{quote})
```

Do NOT add a separate `data:` check in the callback — `_resolve_and_download` handles all special-scheme skipping internally.

---

## Non-negotiable rules

1. Must use `re.sub` with callback.
2. Must use the exact `CSS_URL_PATTERN`.
3. Must reuse shared `_resolve_and_download()` for all URL handling including `data:` skipping.
4. Must pass `urlparse(css_file_base_url).scheme` as the `base_scheme` argument — the third positional argument to `_resolve_and_download`.
5. Must use provided `client` (`httpx.Client` sync).
6. Must use provided `cache: dict`.
7. Must not use cssutils.
8. Must not parse CSS with external libraries.
9. Must preserve original quote style.
10. Must not add a redundant `data:` guard in the callback — special schemes are handled inside `_resolve_and_download`.

---

# Required implementation structure

## Pattern definition

```python
CSS_URL_PATTERN = re.compile(
    r"""url\(\s*(['"]?)([^'"\)]+)\1\s*\)""",
    re.IGNORECASE,
)
```

Do not modify pattern.

---

## Function signature

```python
def rewrite_css_urls(
    css_text: str,
    css_file_base_url: str,
    assets_dir: Path,
    cache: dict,
    client: httpx.Client,
) -> str:
```

Must return rewritten CSS string.

---

## Callback structure

```python
def replace_url(match: re.Match) -> str:
    quote = match.group(1)      # '', '"' or "'" — never None for this pattern
    url_value = match.group(2).strip()

    new_url = _resolve_and_download(
        url_value,
        css_file_base_url,
        urlparse(css_file_base_url).scheme,   # base_scheme — required 3rd argument
        assets_dir,
        cache,
        client,
    )

    return f"url({quote}{new_url}{quote})"
```

Apply:

```python
return CSS_URL_PATTERN.sub(replace_url, css_text)
```

> **[ARCH-DECISION: base_scheme extracted from css_file_base_url]**  
> `_resolve_and_download` has six positional arguments (PRD строки 664–671):  
> `url_value, base_url, base_scheme, assets_dir, cache, client`.  
> `base_scheme` is the third argument and must be passed explicitly as  
> `urlparse(css_file_base_url).scheme` — identical to the call pattern used  
> in `rewrite_asset_urls()` (PRD строки 641–643, 655–657).  
> Omitting it shifts `assets_dir` into the `base_scheme` position, causing  
> wrong protocol resolution for `//cdn.example.com/...` URLs and a type error  
> on any protocol-relative asset.

> **[ARCH-DECISION: no data: guard in callback]**  
> The PRD callback (строки 776–786) calls `_resolve_and_download` directly  
> without a preceding `data:` check. All special-scheme handling  
> (`data:`, `javascript:`, `mailto:`, `tel:`, `#`) is performed inside  
> `_resolve_and_download` (строка 677), which returns the original `url_value`  
> unchanged for these cases. The callback then reconstructs  
> `url({quote}{url_value}{quote})` — identical to the original for well-formed input.  
> Adding a separate `data:` guard returning `match.group(0)` is redundant and  
> diverges from the PRD implementation pattern.

> **[ARCH-DECISION: quote = match.group(1), no `or ""`]**  
> Group `(['"]?)` with `?` quantifier always matches (zero or one character),  
> so `match.group(1)` returns `""` for unquoted URLs, never `None`.  
> The `or ""` fallback is unnecessary and not present in the PRD (строка 777).

---

# `_resolve_and_download` — full signature reference

```python
def _resolve_and_download(
    url_value: str,    # 1 — raw URL from url(...)
    base_url: str,     # 2 — base URL for resolving relative paths
    base_scheme: str,  # 3 — scheme ('http' or 'https') for protocol-relative URLs
    assets_dir: Path,  # 4 — directory to save downloaded assets
    cache: dict,       # 5 — shared abs_url → filename cache
    client: httpx.Client,  # 6 — sync httpx client
) -> str:
```

Always call with all six arguments. Passing five arguments shifts every
parameter after the missing one and causes silent misbehaviour or a TypeError.

---

# URL resolution rules (inside `_resolve_and_download`)

### Skip types — returned as-is

If starts with any of:
- `data:`
- `javascript:`
- `mailto:`
- `tel:`
- `#`

→ return original `url_value` unchanged (handled by `_resolve_and_download`, not the callback).

### Protocol-relative (`//`)

Prepend `base_scheme` → `f"{base_scheme}:{url_value}"`.

### Root-relative (`/`) or relative path

`urljoin(base_url, url_value)`.

### Already absolute (`http://`, `https://`)

Use as-is.

---

# Download logic (shared)

`_resolve_and_download()` must:

1. Normalize to absolute URL.
2. Check `cache[abs_url]`.
3. If cached → return `./assets/{cached_filename}`.
4. Else:
   - `client.get(abs_url)`
   - If `status_code != 200` → log warn, return original `url_value`.
   - On exception → log warn, return original `url_value`.
5. Save file into `assets_dir`.
6. Resolve filename collisions using `_{n}` suffix.
7. Store in cache.

EC-05 applies:
- HTTP != 200 → log warn + keep original.

---

# Quote preservation

Examples:

Input:
```
url("fonts/font.woff2")
url('img/bg.png')
url(bg.png)
```

Output must preserve original quoting:

```
url("assets/font.woff2")
url('assets/bg.png')
url(assets/bg.png)
```

Do not force quotes if none existed.

---

# Correct base resolution

- `css_file_base_url` must be used as `base_url` argument.
- Not the HTML page base URL.
- Each CSS file has its own base URL derived from its own location.

---

# Prohibited patterns

- ❌ Calling `_resolve_and_download` with five arguments (omitting `base_scheme`)
- ❌ Passing `assets_dir` as the third argument to `_resolve_and_download`
- ❌ Adding a `data:` early-return guard in the callback (redundant, diverges from PRD)
- ❌ Using `quote = match.group(1) or ""` (`or ""` is unnecessary for this pattern)
- ❌ Using cssutils
- ❌ Replacing via naive string replace
- ❌ Losing original quotes
- ❌ Ignoring protocol-relative URLs
- ❌ Redownloading cached assets
- ❌ Raising exception on 404
- ❌ Using async client
- ❌ Ignoring relative path resolution

---

# Definition of done

- `CSS_URL_PATTERN` used exactly as defined in PRD
- `re.sub` with callback implemented
- Callback calls `_resolve_and_download` with all six arguments, including `urlparse(css_file_base_url).scheme` as `base_scheme`
- No separate `data:` check in callback — special schemes handled inside `_resolve_and_download`
- `quote = match.group(1)` with no `or ""` fallback
- Quote style preserved in output
- Shared cache respected
- HTTP != 200 logs warn and keeps original
- Uses `css_file_base_url` as `base_url` for resolution
- No external CSS parser used
```
