---
name: playwright-docker-scraper-networkidle
description: Implements Playwright-based scraping in Docker with Chromium launch args, config-driven timeout handling, networkidle partial fallback, lazy-load scrolling, and bot-detection guards. Use when editing backend/worker/module_scraper.py or Playwright navigation logic in Backend / Worker.
---
# playwright-docker-scraper-networkidle

## When to use
Use this skill when working on:

- `backend/worker/module_scraper.py`
- Playwright browser launch configuration
- Page navigation (`goto`)
- networkidle handling
- Lazy-load triggering (scroll)
- Bot detection safeguards
- Early-fail logic in Module 1

Applies only to **AI Landing Page Uniqueizer** worker.

---

## Rationale from PRD

§3.3 (Module 1), §4 M2.1 / M2.2  
EC-01 / EC-02 / EC-03 / EC-04

Required behavior:

- Launch Playwright Chromium with:
  - `--no-sandbox`
  - `--disable-dev-shm-usage`
- `goto()` timeout must use `SCRAPER_PAGE_TIMEOUT_SECONDS * 1000` from `backend.config`.
- `wait_for_load_state('networkidle')` timeout = 45 seconds.
- If networkidle times out → continue with partial DOM (log warn).
- **Trigger lazy loading:** scroll to bottom and wait 2000ms before extracting HTML.
- If URL indicates captcha (redirected AND contains tokens) → fail with "Target URL blocked by anti-bot".
- If `len(html) < 1000` → fail with "Scraped HTML too small, possible bot detection".

---

## Required instruction

Launch Playwright with `args=['--no-sandbox','--disable-dev-shm-usage']`.  
Import `SCRAPER_PAGE_TIMEOUT_SECONDS` and set `goto(timeout=SCRAPER_PAGE_TIMEOUT_SECONDS * 1000)`.  
After `goto` check if `page.url` differs from `target_url` AND contains `captcha|verify|challenge` → fail ("Target URL blocked by anti-bot").  
Wrap `wait_for_load_state('networkidle',timeout=45000)` in try/except, on timeout log warn and continue.  
Execute `page.evaluate("window.scrollTo(0, document.body.scrollHeight)")` and `page.wait_for_timeout(2000)`.  
Check `len(html) < 1000` → fail.

---

## Non-negotiable rules

1. Use async Playwright API.
2. Must use Chromium with Docker-safe launch args.
3. `goto()` timeout MUST use `SCRAPER_PAGE_TIMEOUT_SECONDS * 1000`. Do not hardcode 60000.
4. `networkidle` timeout must be exactly 45000 ms.
5. On networkidle timeout → log warn and continue.
6. On navigation timeout → fail job with "Timeout: target URL unreachable" (EC-01).
7. Captcha detection must check if `page.url` != `target_url` AND contains trigger words.
8. MUST execute scroll to bottom and wait 2000ms after networkidle to trigger lazy loading.
9. If `len(html) < 1000` → fail job.
10. On failure → set `jobs.status='failed'` and log appropriate error message.

---

# Required implementation pattern

## Browser launch

```python
from playwright.async_api import async_playwright

async with async_playwright() as p:
    browser = await p.chromium.launch(
        args=["--no-sandbox", "--disable-dev-shm-usage"],
        headless=True,
    )

    context = await browser.new_context()
    page = await context.new_page()
```

Arguments must match exactly:
- `"--no-sandbox"`
- `"--disable-dev-shm-usage"`

---

## Navigation (EC-01)

```python
from backend.config import SCRAPER_PAGE_TIMEOUT_SECONDS

try:
    await page.goto(target_url, timeout=SCRAPER_PAGE_TIMEOUT_SECONDS * 1000)
except Exception:
    await log_error(job_id, "Timeout: target URL unreachable")
    await fail_job(job_id, "Timeout: target URL unreachable")
    return
```

- Timeout must not be hardcoded.
- Error message must match: `"Timeout: target URL unreachable"`

---

## Captcha detection (EC-03)

Immediately after navigation:

```python
current_url = page.url.lower()

if current_url != target_url.lower() and any(token in current_url for token in ["captcha", "verify", "challenge"]):
    await log_error(job_id, "Target URL blocked by anti-bot")
    await fail_job(job_id, "Target URL blocked by anti-bot")
    return
```

Must check if a redirect occurred (`current_url != target_url.lower()`) AND contains tokens. Message must match exactly.

---

## networkidle handling (EC-02)

```python
try:
    await page.wait_for_load_state("networkidle", timeout=45000)
except Exception:
    await log_warn(job_id, "networkidle timeout, using partial DOM")
```

- Timeout must be 45000.
- On timeout:
  - DO NOT fail job.
  - Log warn: `"networkidle timeout, using partial DOM"`
  - Continue execution.

---

## Lazy-loading & HTML size guard (EC-04)

```python
# Trigger lazy loading
await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
await page.wait_for_timeout(2000)

html = await page.content()

if len(html) < 1000:
    await log_error(job_id, "Scraped HTML too small, possible bot detection")
    await fail_job(job_id, "Scraped HTML too small, possible bot detection")
    return
```

Scroll and wait are mandatory before getting `page.content()`.
Error message must match exactly: `"Scraped HTML too small, possible bot detection"`

---

## Correct execution order

1. Launch browser with required args.
2. `goto(timeout=SCRAPER_PAGE_TIMEOUT_SECONDS * 1000)`
3. Check captcha redirect (`page.url != target_url`).
4. `wait_for_load_state('networkidle', timeout=45000)`
5. Scroll to bottom and wait 2000ms.
6. Get `html`
7. Check length guard.
8. Continue Module 1 processing.

Do not reorder.

---

## Prohibited patterns

- ❌ Missing Docker args
- ❌ Hardcoding `goto` timeout (must use `SCRAPER_PAGE_TIMEOUT_SECONDS * 1000`)
- ❌ Using networkidle timeout ≠ 45000
- ❌ Failing job on networkidle timeout
- ❌ Ignoring captcha redirect or failing without checking if the URL actually changed
- ❌ Missing scroll to bottom / 2000ms wait (breaks lazy loading)
- ❌ Allowing HTML < 1000
- ❌ Using sync Playwright API
- ❌ Letting exception bubble and crash worker

---

## Definition of done

- Chromium launched with exact Docker args
- goto timeout derived from config env var
- networkidle timeout = 45000
- networkidle timeout logs warn and continues
- scroll and wait executed before content extraction
- captcha redirect detection implemented correctly (checks for redirect)
- HTML length guard implemented
- Failure sets job status to `failed`
- Worker loop remains stable
```