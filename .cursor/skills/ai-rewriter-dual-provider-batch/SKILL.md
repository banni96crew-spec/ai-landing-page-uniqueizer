```markdown
---
name: ai-rewriter-dual-provider-batch
description: Implements dual-provider AI rewriting (openai / anthropic) with strict batching, retry/backoff, markdown fence stripping, and length-ratio validation. Use when editing backend/worker/module_ai_rewriter.py in Backend / Worker.
---
# ai-rewriter-dual-provider-batch

## When to use
Use this skill when working on:

- `backend/worker/module_ai_rewriter.py`
- Module 3 (AI Rewriter)
- Provider selection logic
- Batch processing logic
- Retry/backoff handling
- EC-10 – EC-14 implementation

Applies only to **AI Landing Page Uniqueizer** worker.

---

## Rationale from PRD

§3.3, M4.1–M4.6  
EC-10–EC-14

Requirements:

- Two equal providers:
  - `openai`
  - `anthropic`
- `BATCH_SIZE = 20`
- `MAX_TOKENS_PER_BATCH = 3000`
- EC-10: missing API key → fail fast
- EC-11: HTTP 429 → retry 3x with backoff `[1,4,16]`
- EC-12: strip markdown fences
- EC-13: length ratio ∈ `[0.85, 1.15]` else fallback
- EC-14: anthropic package missing → fail

---

## Required instruction

In `module_ai_rewriter.py`:

- Check API key before start (EC-10, fail fast).
- Batch text nodes by `BATCH_SIZE=20`.
- For each batch:
  - On 429 retry with `[1,4,16]` seconds backoff x3.
- Strip markdown:
  ```python
  re.sub(r'```[\w]*\n?(.*?)```', r'\1', resp, flags=re.DOTALL)
  ```
- Check length ratio in `[0.85,1.15]` else use original + log warn.
- Support both `openai.AsyncOpenAI` and `anthropic.AsyncAnthropic`
  via `settings.ai_provider`.
- Pass HTML tags inside text nodes to API as-is; return them unchanged (M4.5).

---

## Non-negotiable rules

1. Providers are equal — no fallback between them.
2. Must use async clients.
3. Must validate API key before any API call.
4. `BATCH_SIZE = 20`.
5. `MAX_TOKENS_PER_BATCH = 3000`.
6. Retry only on HTTP 429.
7. Retry exactly 3 times with delays `[1,4,16]`.
8. Strip markdown fences exactly with required regex.
9. Validate length ratio strictly.
10. On ratio violation → use original + log warn.
11. Worker must not crash.
12. Must copy entire `mutated/` dir to `rewritten/` before rewriting.
13. Model name must be read from `settings.ai_model`, not hardcoded.
14. HTML tags inside text nodes must be forwarded to the API unchanged and preserved in the response (M4.5).

---

# Constants (mandatory)

```python
BATCH_SIZE = 20
MAX_TOKENS_PER_BATCH = 3000
RETRY_BACKOFF = [1, 4, 16]
```

---

# System prompt (mandatory)

Use exactly this `SYSTEM_PROMPT` when calling either provider (PRD §3.3):

```python
SYSTEM_PROMPT = """
You are an expert direct response marketer and copywriter specializing in traffic arbitrage.
RULES:
- Rewrite text: preserve meaning, completely change lexicon (Reframe, Clarify, Amplify)
- Preserve ALL HTML tags within the text fragment unchanged
- Keep output length within ±10% of input character count
- Tone: Engaging, Empathetic, Persuasive. Zero robotic clichés.
- Return ONLY the rewritten fragment, no explanations.
"""
```

Do not alter this prompt. Do not substitute it with a shorter or paraphrased version.

---

# EC-10 — Fail fast on missing API key

Before processing:

```python
if api_key == "":
    log_error(job_id, "AI API key not configured. Visit /settings.")
    fail_job(job_id, "AI API key not configured. Visit /settings.")
    return
```

Must execute before Module 3 logic.

---

# Provider initialization

Model name must be read from `settings.ai_model` — **never hardcoded**.  
PRD M4.6: `openai` uses `settings.ai_model` (default `gpt-4o-mini`); `anthropic` uses `settings.ai_model` (default `claude-haiku`).

## OpenAI

```python
from openai import AsyncOpenAI

model = settings.ai_model  # read from DB settings, e.g. "gpt-4o-mini"
client = AsyncOpenAI(api_key=openai_api_key)
```

## Anthropic

```python
from anthropic import AsyncAnthropic

model = settings.ai_model  # read from DB settings, e.g. "claude-haiku"
client = AsyncAnthropic(api_key=anthropic_api_key)
```

If `anthropic` import fails:

```python
log_error(job_id, "anthropic package not installed")
fail_job(job_id, "anthropic package not installed")
return
```

(EC-14)

---

# Batching logic

```python
for i in range(0, len(text_nodes), BATCH_SIZE):
    batch = text_nodes[i:i + BATCH_SIZE]
```

Each batch:

- Concatenate texts in deterministic format.
- Ensure total tokens <= MAX_TOKENS_PER_BATCH.
- HTML tags inside each text node must be forwarded to the API as-is and preserved
  in the returned result without modification (M4.5).

Do not exceed batch size.

---

# Retry logic (EC-11)

> **[ARCH-DECISION: EC-11 takes precedence over M4.3]**  
> PRD contains an internal conflict:  
> - **M4.3** states: after 3 retry failures → `status='failed'`  
> - **EC-11** (error table) states: after 3 retry failures → skip batch, use original text, `log warn`  
>
> **Resolution: follow EC-11.** EC-11 is the authoritative specification for this exact
> error case (HTTP 429). It is also consistent with rule "Worker must not crash" and
> the general principle of graceful degradation: losing one batch of rewrites is
> preferable to failing the entire job. M4.3 describes the general retry contract;
> EC-11 overrides the terminal action specifically for rate-limit failures.

```python
for attempt, delay in enumerate(RETRY_BACKOFF, start=1):
    try:
        response = await call_provider(...)
        break
    except Some429Exception:
        if attempt == 3:
            log_warn(job_id, "AI rate limit exceeded, using original batch")
            use_original_batch()
            break
        await asyncio.sleep(delay)
```

- Retry only on 429.
- Exactly 3 attempts.
- Backoff: 1 → 4 → 16 seconds.
- After 3 failures → skip batch, use original text, log warn (EC-11).
- Do **not** set `status='failed'` on rate-limit exhaustion.

---

# EC-12 — Strip markdown fences

After receiving response:

```python
clean_text = re.sub(
    r'```[\w]*\n?(.*?)```',
    r'\1',
    resp,
    flags=re.DOTALL,
)
```

Must use:
- Same pattern
- `re.DOTALL`
- Replace with `\1`

---

# EC-13 — Length ratio validation

For each rewritten node:

```python
ratio = len(new_text) / max(len(original_text), 1)

if not (0.85 <= ratio <= 1.15):
    log_warn(
        job_id,
        f"AI text length violated for node {node_index}, using original"
    )
    new_text = original_text
```

Range must be inclusive.

---

# M4.5 — HTML tags inside text nodes

- When sending a text node to the API, include any HTML tags present inside it as-is.
- The API must return them unchanged.
- After receiving the response, verify tags are intact before writing back to DOM.
- Do not strip or escape inner HTML tags during batching or response parsing.

---

# Text node selector

Must match exactly (PRD §3.3):

```python
TEXT_NODES_SELECTOR = [
    'h1','h2','h3','h4','h5','h6',
    'p','button','li','span'
]
```

No additional tags allowed.

---

# Correct execution order

1. Copy `mutated/` → `rewritten/`
2. Load settings (including `ai_provider`, `ai_model`, API keys)
3. Validate API key (EC-10)
4. Initialize provider client using `settings.ai_model`
5. Collect text nodes using `TEXT_NODES_SELECTOR`
6. Batch by `BATCH_SIZE=20`
7. For each batch:
   - Call provider with `SYSTEM_PROMPT`
   - Retry on 429 per EC-11 (skip batch after 3 failures, do not fail job)
   - Strip markdown fences (EC-12)
   - Validate length ratio per EC-13
   - Preserve HTML tags inside nodes (M4.5)
8. Write rewritten text back to DOM
9. Log `MODULE_AI_REWRITER_DONE`

---

# Prohibited patterns

- ❌ Single-provider hardcoding
- ❌ Fallback provider switching
- ❌ Batch size ≠ 20
- ❌ Missing retry logic
- ❌ Retrying non-429 errors
- ❌ Not stripping markdown fences
- ❌ Using different regex
- ❌ Ignoring ratio check
- ❌ Accepting ratio outside range
- ❌ Crashing on API failure
- ❌ AST-based DOM rewriting
- ❌ Hardcoding model name instead of reading from `settings.ai_model`
- ❌ Omitting `SYSTEM_PROMPT` or substituting it with a different prompt
- ❌ Stripping or escaping HTML tags inside text nodes before sending to API
- ❌ Setting `status='failed'` on HTTP 429 rate-limit exhaustion (use skip+warn per EC-11)

---

# Definition of done

- Both providers supported equally
- API key checked before execution
- `BATCH_SIZE = 20` enforced
- `MAX_TOKENS_PER_BATCH = 3000` enforced
- Model read from `settings.ai_model`
- `SYSTEM_PROMPT` used verbatim for all API calls
- Retry logic with `[1,4,16]` backoff
- After 3 x 429 failures: skip batch + log warn (EC-11), job continues
- Markdown fences stripped (EC-12)
- Ratio validated `[0.85,1.15]`, violations fallback to original (EC-13)
- HTML tags inside text nodes preserved through API round-trip (M4.5)
- EC-14 implemented
- Worker remains stable
```
