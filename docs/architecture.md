## 1. High-Level Architecture Overview


Architectural Pattern: Modular Monolith with an asynchronous background worker (event-driven in-process) and a state machine pipeline.


The system is implemented as:


- Backend: FastAPI (Python 3.12) + built-in async worker (in the same OS process as the HTTP server).
- Database: SQLite (WAL mode) — the sole source of task state.
- Worker Model: Polling + atomic claim (UPDATE ... WHERE status='pending') → state machine (pending → running → done|failed).
- Frontend: Next.js 14 (App Router) + React 18 + Tailwind v4.
- **Realtime:** WebSocket (`/ws/logs/{job_id}`) + fallback polling.
- **Deployment:** Single Docker container (backend + frontend), docker-compose.


The architecture is focused on:
- self-hosted single-tenant deployment,
- limited concurrency (`WORKER_CONCURRENCY ≤ 4`),
- CPU-bound + I/O-bound pipeline with job_id isolation.


---


## 2. Component Decomposition


### 2.1 Frontend (Next.js 14)


- **Purpose:**
- Task creation (URL input).
- Display status, progress, and logs.
- Manage AI provider settings.
- Download ZIP artifact.


- **Technologies:**
- `next@14`, `react@18`, `tailwindcss@4`, `framer-motion@11`, `typescript@5`.


- **Interfaces:**
- REST → `/api/*`
- WebSocket → `/ws/logs/{job_id}`


---


### 2.2 Backend API Layer (FastAPI)


- **Purpose:**
- CRUD tasks (`/api/jobs`).
- Settings management (`/api/settings`).
- Artifact output (`/api/artifacts/...`).
- SSRF protection and rate limiting.
- WebSocket log streaming.


- **Technologies:**
- `fastapi==0.115.0`
- `uvicorn`
- `pydantic v2`
- `sqlite3` (raw, WAL mode)
- `CORSMiddleware`


- **Interfaces:**
- REST (HTTP JSON)
- WebSocket (JSON stream)


---


### 2.3 Worker (Pipeline Engine)


- **Purpose:**
- Implementation of a 5-stage pipeline:
1. Scraper
2. DOM Mutator
3. AI Rewriter
4. Media Uniqueizer
5. Packer
- Updating task statuses.
- Writing logs and progress markers.
- Timeout management (`asyncio.wait_for`).


- **Technologies:**
- asyncio
- Playwright (Chromium)
- BeautifulSoup4 + lxml
- httpx (async asset download)
- Pillow + numpy
- openai >=1.50.0
- anthropic >=0.34.0
- zipfile, hashlib (stdlib)


- **Interfaces:**
- DB polling (SQLite)
- Internal Pub/Sub via `JOB_QUEUES: dict[int, asyncio.Queue]`


---


### 2.4 Database (SQLite)


- **Purpose:**
- Job persistence (`jobs`)
- Artifacts (`artifacts`)
- Settings (`settings`)
- Logs (`logs`)
- Calculating `progress_pct` using markers


- **Technologies:**
- SQLite
- WAL mode
- Foreign keys
- Trigger `trg_jobs_updated_at`


- **Interfaces:**
- SQL (via raw sqlite3 connection)


---


### 2.5 File Storage Layer


- **Purpose:**
- Temporary working directories:
- `{JOBS_WORKDIR}/{job_id}/raw`
- `cleaned/`
- `mutated/`
- `rewritten/`
- Final ZIP artifacts:
- `{ARTIFACTS_DIR}/{job_id}.zip`


- **Technologies:**
- Local file system inside Docker
- `shutil`, `zipfile`


- **Interfaces:**
- POSIX FS operations


---


### 2.6 External Integrations


#### 2.6.1 AI Providers


- **Purpose:**
- Batch rewriting of DOM text nodes.


- **Technologies:**
- OpenAI (`gpt-4o-mini`)
- Anthropic (`claude-3-haiku-20240307`)


- **Interfaces:**
- HTTPS JSON API (chat completions / messages API)
- Retry + fallback policy


---


#### 2.6.2 Target Landing (Scraping Target)


- **Purpose:**
- Obtaining HTML and assets from the landing page.


- **Technologies:**
- Playwright headless Chromium
- httpx async streaming


- **Interfaces:**
- HTTP/HTTPS


---


## 3. Data Flow & Integration


### 3.1 User Story: “Unique the landing page URL”


#### Step 1: Create a task


1. Frontend → `POST /api/jobs`
2. Backend:
- Validates the URL (http/https, SSRF blocklist).
- Checks the rate limit and queue size.
- Creates `jobs(status='pending')`.


---


#### Step 2: Capturing a task by a worker


1. Worker loop:
```sql
UPDATE jobs
SET status='running'
WHERE id = (
SELECT id FROM jobs
WHERE status='pending'
ORDER BY created_at
LIMIT 1
)
```
2. Create `JOB_QUEUES[job_id]`.
3. Write `MARKER:pipeline_started`.


---


#### Step 3: Module 1 — Scraper


- Playwright → DOM snapshot.
- rewrite_asset_urls() → resource localization.
- Check:
- `ASSET_MAX_SIZE_BYTES`
- `MAX_PAGE_SIZE_MB`
- Output → `raw/` + `cleaned/`
- Log → `MARKER:scraper_done`.


**Business Goal:** Remove trackers and external dependencies → Reduce footprint.


---


#### Step 4: Module 2 — DOM Mutator


- Build `selector_map`.
- Rename CSS/HTML/JS selectors.
- Inject DOM noise.
- Output → `mutated/`
- Log → `MARKER:mutator_done`.


**Business Goal:** Obfuscate the structure to bypass signature analysis.


---


#### Step 5: Module 3 — AI Rewriter


- Extract text nodes (>10 characters).
- Batch → AI provider.
- Retry + fallback.
- Length check ±15%.
- Output → `rewritten/index.html`
- Log → `MARKE`
R:rewriter_done`.


**Business Goal:** Semantic content uniqueization.


---


#### Step 6: Module 4 — Media Uniqueizer


- JPEG/PNG/WEBP:
- Strip metadata,
- Crop 1px,
- Inject Gaussian noise.
- In-place rewrite.
- Log → `MARKER:media_done`.


**Business Goal:** Change digital image hashes.


---


#### Step 7: Module 5 — Packer


- Check disk space.
- ZIP all `rewritten/`.
- SHA256 hash.
- INSERT into `artifacts`.
- `jobs.status='done'`.
- Log → `MARKER:packer_done`.
- Cleanup `{JOBS_WORKDIR}/{job_id}/`.


---


### 3.2 Real-time Log Streaming


1. Worker writes to:
- `logs` (SQLite)
- `JOB_QUEUES[job_id]` (async queue)
2. WebSocket:
- Sends the last 500 logs.
- Then streams new ones from the queue.
3. On `done/failed`:
- Sends `{type:"done"}`.


Fallback: polling `GET /api/jobs/{id}`.


---


### 3.3 Progress Calculation


`progress_pct`:


- `pending` → 0
- `running|failed` → `COUNT(done_markers) × 18`
- `done` → 100


Source of truth: the `logs` table.


---


## 4. Architectural Decisions (ADR)


### ADR-1: Modular Monolith vs. Microservices


**Reason:**
- Self-hosted single-node product.
- SQLite.
- No multi-tenant requirements.


**Effect:**
- Minimal infrastructure complexity.
- Ease of deployment (1 container).


---


### ADR-2: SQLite + WAL


**Reason:**
- Low load (WORKER_CONCURRENCY ≤ 4).
- Simplicity of self-hosted.
- No need for a separate database service.


**Compensation:**
- Each logging operation opens a separate connection.
- timeout=10 for releasing locks.


---


### ADR-3: Worker in the same process


**Reason:**
- MVP.
- Simplified operation.
- No Celery/Redis.


**Limitation:**
- No horizontal scaling.
- Resume is not supported (EC-16).


---


### ADR-4: State Machine via `jobs.status`


**Reason:**
- Pipeline predictability.
- Explicit lifecycle model.
- Simple diagnostics.


---


### ADR-5: AI Fallback Policy (Primary → Retry → Fallback)


**Reason:**
- Ensuring rate limit tolerance.
- Minimizing failed tasks.


**Business Result:**
- Increased percentage of successfully completed uniqueizations.


---


### ADR-6: Local File Storage


**Reason:**
- Self-hosted.
- No HA requirements.
- Artifact size limited by TTL.


---


### ADR-7: WebSocket + Polling Fallback


**Reason:**
- Real-time UX.
- Guaranteed status updates when WS is unavailable.


---


## Verifying compliance with business goals


| Business goal | Architectural Component |
|-------------|-------------------------|
| HTML/CSS Footprint Removal | Module 2 (DOM Mutator) |
| Semantic Uniqueization | Module 3 (AI Rewriter) |
| Image Uniqueization | Module 4 (Media Uniqueizer) |
| CDN Digital Footprint Minimization | Module 1 (Asset Localization) |
| Fast Execution (3–5 minutes) | Async Worker + Limited Concurrency |
| Self-hosted Deployment | Docker + SQLite + Single Container |
| Progress Monitoring | Logs + WebSocket + Progress Markers |
| Reliability | Retry Policy + Timeout + Fallback Logic |