```markdown
---
name: google-fonts-self-host-download
description: Implements download_google_fonts() to self-host Google Fonts by fetching CSS with a Windows User-Agent, extracting .woff2 URLs via regex, downloading them into cleaned/assets/fonts/, and replacing @import with local @font-face rules. Use when editing backend/worker/module_scraper.py font handling logic in Backend / Worker.
---
# google-fonts-self-host-download

## When to use
Use this skill when working on:

- `backend/worker/module_scraper.py`
- Google Fonts processing
- `download_google_fonts()`
- Font asset rewriting in Module 1
- M2.5 implementation

Applies only to **AI Landing Page Uniqueizer** worker.

---

## Rationale from PRD

§3.3, M2.5:

- Fetch Google Fonts CSS via HTTP GET.
- Must send User-Agent:
  ```
  Mozilla/5.0 (Windows NT 10.0; Win64; x64)
  ```
- Extract `.woff2` URLs using regex:
  ```python
  re.findall(r'url\((https://fonts\.gstatic\.com/[^)]+\.woff2)\)', css)
  ```
- Download fonts into:
  ```
  cleaned/assets/fonts/
  ```
- Replace original `@import url(...)` with:
  ```
  @font-face { src: url('./assets/fonts/{filename}') }
  ```
- On any error:
  - log warn
  - return empty string

---

## Required instruction

In `download_google_fonts(css_url, fonts_dir)`:

- GET with:
  ```python
  headers={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
  ```
- Extract `.woff2` URLs via regex.
- Download each to `fonts_dir`.
- Replace original `@import url(...)` with:
  ```
  @font-face { src: url('./assets/fonts/{filename}') }
  ```
- On any error: log warn, return empty string.

---

## Non-negotiable rules

1. Use sync `httpx.Client`.
2. Must include required User-Agent header.
3. Must extract only `.woff2` URLs from `fonts.gstatic.com`.
4. Must save files into `cleaned/assets/fonts/`.
5. Must not keep remote Google Fonts URLs.
6. On any error → log warn + return `""`.
7. Must not crash worker.
8. Must not use external CSS libraries.
9. Must not silently ignore failures without logging.

---

# Required implementation structure

## Function signature

```python
def download_google_fonts(
    css_url: str,
    fonts_dir: Path,
) -> str:
```

Returns rewritten CSS string or empty string on error.

---

## HTTP request

```python
import httpx

try:
    with httpx.Client(timeout=30) as client:
        resp = client.get(
            css_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
            },
        )
        if resp.status_code != 200:
            log_warn(job_id, f"Google Fonts CSS download failed: {css_url}")
            return ""
        css_text = resp.text
except Exception:
    log_warn(job_id, f"Google Fonts CSS download failed: {css_url}")
    return ""
```

User-Agent must match exactly.

---

## Extract woff2 URLs

Must use:

```python
font_urls = re.findall(
    r'url\((https://fonts\.gstatic\.com/[^)]+\.woff2)\)',
    css_text,
)
```

Only `.woff2` allowed.

---

## Download font files

For each URL:

```python
for font_url in font_urls:
    filename = Path(urlparse(font_url).path).name
    font_path = fonts_dir / filename

    try:
        r = client.get(font_url)
        if r.status_code != 200:
            log_warn(job_id, f"Font download failed: {font_url}")
            return ""
        font_path.write_bytes(r.content)
    except Exception:
        log_warn(job_id, f"Font download failed: {font_url}")
        return ""
```

- Must save into `fonts_dir`
- Must create directory if missing
- On any failure → log warn + return `""`

---

## Replace @import

Original pattern example:

```css
@import url('https://fonts.googleapis.com/css2?...');
```

Must replace with:

```css
@font-face {
  src: url('./assets/fonts/{filename}');
}
```

For multiple fonts:
- Generate one `@font-face` block per `.woff2`.

Example output:

```css
@font-face {
  src: url('./assets/fonts/abc123.woff2');
}
@font-face {
  src: url('./assets/fonts/def456.woff2');
}
```

Do not preserve original `@import`.

---

## Path rule

Must use:

```
'./assets/fonts/{filename}'
```

Not absolute path.
Not raw_dir path.
Not remote URL.

---

## Error handling (mandatory)

On any of the following:

- CSS request fails
- CSS status != 200
- Font request fails
- Font status != 200
- Write error
- Regex failure

→ Must:

```python
log_warn(job_id, "Google Fonts processing failed")
return ""
```

Worker must continue without fonts.

---

## Prohibited patterns

- ❌ Missing required User-Agent
- ❌ Using async client
- ❌ Keeping remote fonts.gstatic.com URLs
- ❌ Ignoring download errors
- ❌ Raising exception upward
- ❌ Saving outside cleaned/assets/fonts/
- ❌ Using non-woff2 fonts
- ❌ Using cssutils

---

## Definition of done

- CSS fetched with exact Windows User-Agent
- `.woff2` URLs extracted via required regex
- Fonts downloaded into `cleaned/assets/fonts/`
- `@import` replaced with local `@font-face`
- On any error → log warn + return empty string
- Worker never crashes
```