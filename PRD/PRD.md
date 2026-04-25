# PRD: AI Landing Page Uniqueizer — MVP
### Single Source of Truth для Cursor AI


---


## 0.1 Диаграммы и витрины (экспорт)


Визуальные диаграммы дублируют §2–§3 этого файла:


| Формат | Путь в репозитории |
|--------|-------------------|
| Markdown + Mermaid (PR / диффы) | `docs/architecture.md`, `docs/database.md` |
| HTML-фрагменты (Canvas / встраивание) | `docs/html/architecture.html`, `docs/html/database.html` |


**Правило согласованности:** при правке смысла сначала обновляется этот файл (`PRD_v3.0`), затем перечисленные `docs/*`. При противоречии приоритет: **§3.2 DDL** > диаграммы > прочий текст.


---


## 0. Preface для Cursor


> **Инструкция по использованию:** Каждый раздел этого документа написан как атомарная задача. Используй `## Module N` как контекст для отдельного промпта в Composer. Все имена переменных, роутов и компонентов — окончательные. Не переименовывай без явной пометки `[RENAME_OK]`.


> **Единственный источник истины по схеме `logs`:** §3.2. Поля: `id`, `job_id`, `level`, `message`, `timestamp`. Любые упоминания `module_name`, `marker_type`, `detail` в старых версиях — удалены и недействительны.


---


## 1. Executive Summary


**Продукт:** Self-hosted Web инструмент для арбитражников, автоматизирующий парсинг landing page по URL и её многоуровневую уникализацию (HTML/CSS обфускация, AI-рерайтинг текста, модификация медиафайлов) с выдачей готового ZIP-архива.


**Ценность:** Заменяет 4–8 часов ручной работы верстальщика одной операцией длительностью 3–5 минут, устраняя цифровые следы (footprints) по всем известным векторам анализа рекламных сетей.


---


## 2. Core Logic & Pipeline


> **CoT-обоснование:** Линейный пайплайн описан как конечный автомат (state machine) со строгими переходами статусов. Это позволяет генерировать воркер как единый `while True` цикл с `match/case` по статусу задачи, без сложной оркестрации.


---


### Диаграмма потока данных


```
[USER: URL Input]
│
▼
[API: POST /api/jobs]
│  Валидация target_url:
│  - только http:// и https://
│  - запрет private IP (RFC1918: 10.x, 172.16-31.x, 192.168.x)
│  - запрет loopback (127.x, ::1)
│  - запрет link-local (169.254.x — AWS/GCP metadata)
│
├──► [Rate Limit: 10 req/min per IP → HTTP 429 {"error": "rate_limit_exceeded"}]
└──► [Queue Guard: COUNT(pending) >= MAX_QUEUE_SIZE → HTTP 429 {"error": "queue_full"}]
│
▼
[DB: jobs.status = 'pending']
│
▼
[WORKER: polls DB every WORKER_POLL_INTERVAL seconds]
[concurrency = WORKER_CONCURRENCY]
│
│ Атомарный захват задачи (claim):
│   UPDATE jobs SET status='running', updated_at=CURRENT_TIMESTAMP 
│  WHERE id = (SELECT id FROM jobs WHERE status='pending' ORDER BY │created_at LIMIT 1) 
│RETURNING id;
│   — если rowcount=0, воркер пропускает итерацию.
│
│ JOB_QUEUES[job_id] = asyncio.Queue(maxsize=1000)
│ log(job_id, 'info', 'MARKER:pipeline_started')
│
├─► STEP 1: MODULE_SCRAPER
│     Playwright headless Chromium → networkidle → DOM snapshot
│       timeout: SCRAPER_PAGE_TIMEOUT_SECONDS (default: 60)
│     Проверка суммарного объёма assets:
│       если total_assets_size > MAX_PAGE_SIZE_MB →
│         status='failed', message='Page size exceeds limit', cleanup, stop.
│     BeautifulSoup4/lxml:
│       strip trackers (EasyPrivacy + явный список:
│         google-analytics.com, googletagmanager.com, facebook.net,
│         hotjar.com, mc.yandex.ru, connect.facebook.net,
│         pixel.facebook.com, analytics.tiktok.com)
│       strip external fonts
│       strip HTML-комментарии
│     rewrite_asset_urls():
│       обрабатывает атрибуты: src, href, action, data-src, data-href
│       обрабатывает srcset (парсинг по запятой, замена каждого URL)
│       per-asset лимит: ASSET_DOWNLOAD_TIMEOUT_SECONDS, ASSET_MAX_SIZE_BYTES
│     rewrite_css_urls(): обрабатывает url() в скачанных CSS-файлах
│     [KNOWN_LIMITATION: JS-управляемые URL (fetch(), dynamic import(),
│      inline style url()) не перезаписываются — §8 Out of Scope]
│     Linked HTML глубины 1 (/thank-you.html, /privacy.html и т.д.):
│       скачиваются в raw/secondary/, копируются без обработки.
│     Output: {JOBS_WORKDIR}/{job_id}/raw/
│             {JOBS_WORKDIR}/{job_id}/cleaned/
│     log(job_id, 'info', 'MARKER:scraper_done')
│
├─► STEP 2: MODULE_DOM_MUTATOR
│     [CPU-bound → выполняется через run_in_executor]
│     build_selector_map():
│       источник 1 (primary): class="", id="" атрибуты из index.html
│       источник 2 (secondary): селекторы из CSS-файлов
│       объединить, дедуплицировать
│       пропустить префиксы из js_class_exclusion_prefixes
│     apply_mutations(): замена в HTML + CSS + JS по JS_REPLACE_PATTERNS
│     inject_dom_noise(): hidden <div>s + CSS-правила в <head>
│     Output: {JOBS_WORKDIR}/{job_id}/mutated/
│     log(job_id, 'info', 'MARKER:mutator_done')
│
├─► STEP 3: MODULE_AI_REWRITER
│     Extract text nodes: h1-h6, p, button, li, span (только если >10 символов)
│     Batch → AI провайдер (политика: §2 AI Provider Policy)
│     Inject rewritten text back into DOM
│     При ошибке API: fallback = оригинальный текст ноды, продолжить.
│     Output: {JOBS_WORKDIR}/{job_id}/rewritten/
│       (копирует полную структуру из mutated/ → rewritten/
│        включая assets/ и secondary/;
│        перезаписывает только index.html с rewritten-текстом)
│     log(job_id, 'info', 'MARKER:rewriter_done')
│
├─► STEP 4: MODULE_MEDIA_UNIQUEIZER
│     [CPU-bound → выполняется через run_in_executor]
│     Читает изображения из rewritten/assets/images/
│     Форматы: .jpg/.jpeg, .png, .webp
│     GIF, SVG — пропускать (log warn)
│     Pillow:
│       strip metadata (convert RGB → numpy array → fromarray, очищает все чанки)
│       crop 1px (w-1, h-1)
│       inject noise: np.random.normal(0, noise_intensity * 255, shape)
│         clamp к [0, 255], dtype=uint8
│         noise_intensity берётся из settings['noise_intensity'] (default: 0.01)
│     In-place: перезаписывает файлы в rewritten/assets/images/
│     log(job_id, 'info', 'MARKER:media_done')
│
└─► STEP 5: MODULE_PACKER
      Проверка свободного места:
        если disk_free < estimated_zip_size →
          status='failed', message='Insufficient disk space', stop.
      zipfile → {ARTIFACTS_DIR}/{job_id}.zip
      Упаковывает rewritten/ целиком (index.html + assets/ + secondary/)
      DB: artifacts INSERT + jobs.status = 'done'
      log(job_id, 'info', 'MARKER:packer_done')
      JOB_QUEUES.pop(job_id, None)
      Cleanup: удалить {JOBS_WORKDIR}/{job_id}/
```


> **Cleanup при любом завершении (finally-блок воркера):**
> ```python
> finally:
>     shutil.rmtree(Path(JOBS_WORKDIR) / str(job_id), ignore_errors=True)
>     JOB_QUEUES.pop(job_id, None)
> ```
> Директории задач со статусом `failed` **не удаляются автоматически** immediately — сохраняются для отладки. Автоочистка: фоновая задача в `lifespan` удаляет директории `failed`-задач старше `FAILED_JOB_TTL_DAYS` дней. ZIP-артефакты (`done`-задачи) удаляются через `ARTIFACT_TTL_DAYS` дней.


---


### Политика AI-провайдера (MODULE_AI_REWRITER)


**Primary:** OpenAI GPT-4o-mini (`openai_model` из settings).
**Fallback:** Anthropic Claude (`anthropic_model` из settings).


**Логика переключения:**
Если primary вернул HTTP 429, HTTP 5xx или не ответил за `AI_REQUEST_TIMEOUT_SECONDS` — один retry на primary, затем один вызов к fallback с тем же промптом и batch.


**Политика при полном отказе обоих провайдеров:**
Fallback на оригинальный текст ноды для данного batch, pipeline продолжается.
Лог: `log(job_id, 'error', 'Both providers failed, batch N using original text')`.


**Размер batch:** `AI_BATCH_SIZE` env (default: `20` нод). Каждый batch — отдельный API-вызов с независимой политикой retry.


**Порог отказа модуля:** если `failed_batches / total_batches > REWRITE_FAIL_THRESHOLD` → `status='failed'`. Иначе — pipeline продолжается, log warn.


---


### Переменные окружения (полный список)


| Переменная | Default | Описание |
|---|---|---|
| `JOBS_WORKDIR` | `/app/volumes/jobs` | Базовая директория для рабочих файлов задач |
| `ARTIFACTS_DIR` | `/app/volumes/artifacts` | Директория для финальных ZIP-файлов |
| `DATABASE_URL` | `/app/data/app.db` | Путь к SQLite файлу |
| `JOB_TIMEOUT_SECONDS` | `600` | Таймаут всего pipeline на задачу |
| `WORKER_CONCURRENCY` | `2` | Максимальное число параллельно обрабатываемых задач |
| `WORKER_POLL_INTERVAL` | `2` | Интервал опроса БД воркером (секунды) |
| `MAX_PAGE_SIZE_MB` | `50` | Суммарный лимит всех assets одной страницы (MB) |
| `ASSET_MAX_SIZE_BYTES` | `52428800` | Лимит одного скачиваемого файла (bytes, default 50MB) |
| `MAX_QUEUE_SIZE` | `100` | Максимальное число задач со статусом `pending` |
| `SCRAPER_PAGE_TIMEOUT_SECONDS` | `60` | Таймаут Playwright page.goto() |
| `ASSET_DOWNLOAD_TIMEOUT_SECONDS` | `15` | Таймаут одного httpx-запроса при скачивании ассета |
| `AI_REQUEST_TIMEOUT_SECONDS` | `30` | Таймаут одного API-вызова к AI-провайдеру |
| `AI_BATCH_SIZE` | `20` | Число текстовых нод в одном batch-запросе к AI |
| `REWRITE_FAIL_THRESHOLD` | `0.5` | Доля failed batches для перевода задачи в failed |
| `CORS_ORIGINS` | `http://localhost:3000` | CSV-строка разрешённых origins |
| `ARTIFACT_TTL_DAYS` | `7` | Дней хранения ZIP-артефактов done-задач |
| `FAILED_JOB_TTL_DAYS` | `7` | Дней хранения директорий failed-задач |


> **Примечание по `WORKER_CONCURRENCY`:** Playwright запускает отдельный процесс Chromium на каждую задачу. При `WORKER_CONCURRENCY=2` пиковое потребление RAM ≈ 1.5–2 GB. Не рекомендуется значение выше 4 без мониторинга OOM.


> **Разграничение лимитов размера:**
> - `MAX_PAGE_SIZE_MB` — суммарный размер всех скачанных assets задачи (проверяется после завершения scrape).
> - `ASSET_MAX_SIZE_BYTES` — лимит одного файла при стриминге (проверяется инкрементально в `_resolve_and_download_async`).
> Оба лимита независимы. Пример: 100 файлов по 1MB каждый (100MB суммарно) — каждый пройдёт per-asset проверку, но задача упадёт по суммарному лимиту.


---


### Статусная машина задачи (jobs.status)


| Статус | Триггер | Следующий |
|---|---|---|
| `pending` | POST /api/jobs | `running` |
| `running` | Воркер выполнил атомарный `UPDATE … FOR UPDATE SKIP LOCKED` | `done` или `failed` |
| `done` | Module 5 (Packer) завершён | terminal |
| `failed` | Необработанное исключение, таймаут pipeline, превышение лимитов | terminal |


---


### Схема таблицы `logs` (единственная, финальная)


```sql
CREATE TABLE IF NOT EXISTS logs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id    INTEGER NOT NULL REFERENCES jobs(id),
    level     TEXT    NOT NULL DEFAULT 'info', -- 'info' | 'warn' | 'error'
    message   TEXT    NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_logs_job_id_timestamp ON logs (job_id, timestamp);
```


**Маркеры прогресса** пишутся воркером как обычные лог-записи с `level='info'`:


| Момент | message | Модуль |
|---|---|---|
| Старт пайплайна | `MARKER:pipeline_started` | runner.py |
| Module 1 завершён | `MARKER:scraper_done` | module_scraper.py |
| Module 2 завершён | `MARKER:mutator_done` | module_dom_mutator.py |
| Module 3 завершён | `MARKER:rewriter_done` | module_ai_rewriter.py |
| Module 4 завершён | `MARKER:media_done` | module_media.py |
| Module 5 завершён | `MARKER:packer_done` | module_packer.py |


**Формула `progress_pct`** (единственная, для всех статусов):
```sql
SELECT COUNT(*) FROM logs
WHERE job_id = ?
  AND message IN (
    'MARKER:scraper_done',
    'MARKER:mutator_done',
    'MARKER:rewriter_done',
    'MARKER:media_done',
    'MARKER:packer_done'
  )
-- результат * 20 = progress_pct (0→20→40→60→80)
-- status='pending' → принудительно 0
-- status='done'    → принудительно 100
```


---


### Файловая структура директорий по модулям


```
{JOBS_WORKDIR}/{job_id}/
├── raw/                    # Module 1 output: оригинальный DOM + assets
│   ├── index.html
│   ├── secondary/          # Linked HTML глубины 1, без обработки
│   │   ├── thank-you.html
│   │   └── privacy.html
│   └── assets/
│       ├── css/
│       ├── js/
│       ├── fonts/
│       └── images/
├── cleaned/                # Module 1 output: после strip trackers/fonts/comments
│   ├── index.html
│   ├── secondary/
│   └── assets/
│       ├── css/
│       ├── js/
│       ├── fonts/          # скачанные Google Fonts (.woff2)
│       └── images/
├── mutated/                # Module 2 output: после CSS обфускации и DOM noise
│   ├── index.html
│   ├── secondary/
│   └── assets/
│       ├── css/
│       ├── js/
│       ├── fonts/
│       └── images/
└── rewritten/              # Module 3 source + Module 4 in-place + Module 5 source
    ├── index.html          # после AI рерайтинга
    ├── secondary/          # скопированы as-is из mutated/
    └── assets/
        ├── css/
        ├── js/
        ├── fonts/
        └── images/         # Module 4 перезаписывает файлы здесь in-place
```


> **[ARCH-DECISION]:** Module 3 копирует полную структуру `mutated/` → `rewritten/` включая все assets и secondary/. Module 4 перезаписывает изображения in-place в `rewritten/assets/images/`. Module 5 упаковывает `rewritten/` целиком.


> **[KNOWN_LIMITATION]:** Многостраничные лендинги — ограничение MVP. Pipeline обрабатывает только `index.html`. Вторичные HTML (глубина 1) включаются в ZIP без обработки. Задокументировано в §8 Out of Scope.


---






---


## 3. Technical Architecture


### 3.1 Backend: FastAPI Route Specifications


#### Файловая структура Backend


```
backend/
├── main.py           # FastAPI app init, CORS, lifespan
├── state.py          # JOB_QUEUES singleton — единственная точка определения
├── config.py         # Централизованная конфигурация из env
├── database.py       # SQLite connection (raw sqlite3), WAL mode init
├── models.py         # sqlite3.Row → dict row factories
├── schemas.py        # Pydantic v2 request/response models
├── routers/
│   ├── jobs.py       # /api/jobs CRUD
│   ├── settings.py   # /api/settings UPSERT
│   └── artifacts.py  # /api/artifacts download
├── worker/
│   ├── runner.py          # Main polling loop
│   ├── module_scraper.py  # Module 1
│   ├── module_dom_mutator.py  # Module 2
│   ├── module_ai_rewriter.py  # Module 3
│   ├── module_media.py    # Module 4
│   └── module_packer.py   # Module 5
└── ws/
    └── log_broadcaster.py # WebSocket log stream
```


---


#### `backend/state.py`


```python
# backend/state.py
# ЕДИНСТВЕННАЯ точка определения JOB_QUEUES.
# Все модули импортируют отсюда.
# Недопустимо определять JOB_QUEUES в main.py или любом другом модуле.
import asyncio


JOB_QUEUES: dict[int, asyncio.Queue] = {}
```


Импорт во всех потребителях:
```python
from backend.state import JOB_QUEUES
```


---


#### `backend/config.py`


```python
import os
from pathlib import Path


JOBS_WORKDIR                 = Path(os.environ.get("JOBS_WORKDIR", "/app/volumes/jobs"))
ARTIFACTS_DIR                = Path(os.environ.get("ARTIFACTS_DIR", "/app/volumes/artifacts"))
DATABASE_URL                 = os.environ.get("DATABASE_URL", "/app/data/app.db")
WORKER_POLL_INTERVAL         = int(os.environ.get("WORKER_POLL_INTERVAL", "2"))
WORKER_CONCURRENCY           = int(os.environ.get("WORKER_CONCURRENCY", "2"))
JOB_TIMEOUT_SECONDS          = int(os.environ.get("JOB_TIMEOUT_SECONDS", "600"))
MAX_PAGE_SIZE_MB             = int(os.environ.get("MAX_PAGE_SIZE_MB", "50"))
ASSET_MAX_SIZE_BYTES         = int(os.environ.get("ASSET_MAX_SIZE_BYTES", str(50 * 1024 * 1024)))
MAX_QUEUE_SIZE               = int(os.environ.get("MAX_QUEUE_SIZE", "100"))
SCRAPER_PAGE_TIMEOUT_SECONDS = int(os.environ.get("SCRAPER_PAGE_TIMEOUT_SECONDS", "60"))
ASSET_DOWNLOAD_TIMEOUT_SECONDS = int(os.environ.get("ASSET_DOWNLOAD_TIMEOUT_SECONDS", "15"))
AI_REQUEST_TIMEOUT_SECONDS   = int(os.environ.get("AI_REQUEST_TIMEOUT_SECONDS", "30"))
AI_BATCH_SIZE                = int(os.environ.get("AI_BATCH_SIZE", "20"))
REWRITE_FAIL_THRESHOLD       = float(os.environ.get("REWRITE_FAIL_THRESHOLD", "0.5"))
ARTIFACT_TTL_DAYS            = int(os.environ.get("ARTIFACT_TTL_DAYS", "7"))
FAILED_JOB_TTL_DAYS          = int(os.environ.get("FAILED_JOB_TTL_DAYS", "7"))


# CORS: CSV-строка. Пустая строка = запретить все cross-origin запросы.
# В production заменить на конкретные домены.
CORS_ORIGINS: list[str] = [
    o.strip() for o in
    os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
    if o.strip()
]


# SSRF: запрещённые диапазоны для target_url
BLOCKED_IP_PREFIXES = (
    "10.", "172.16.", "172.17.", "172.18.", "172.19.",
    "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
    "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
    "172.30.", "172.31.",
    "192.168.", "127.", "0.", "169.254.", "::1", "fc00:", "fe80:",
)


def get_job_dir(job_id: int) -> Path:
    return JOBS_WORKDIR / str(job_id)


def get_artifact_path(job_id: int) -> Path:
    return ARTIFACTS_DIR / f"{job_id}.zip"
```


---


#### `backend/main.py` — lifespan


```python
from contextlib import asynccontextmanager
from backend.database import init_db, get_connection
from backend.config import CORS_ORIGINS, ARTIFACT_TTL_DAYS, FAILED_JOB_TTL_DAYS
from backend.config import get_job_dir, get_artifact_path
import asyncio, shutil


async def _ttl_cleanup_loop():
    """Фоновая задача: удаляет устаревшие артефакты и директории failed-задач."""
    while True:
        await asyncio.sleep(86400)  # раз в 24 часа
        conn = get_connection()
        try:
            # Удалить ZIP-артефакты done-задач старше ARTIFACT_TTL_DAYS
            rows = conn.execute(
                "SELECT id FROM jobs WHERE status='done' "
                "AND updated_at < datetime('now', ?)",
                (f"-{ARTIFACT_TTL_DAYS} days",)
            ).fetchall()
            for row in rows:
                get_artifact_path(row["id"]).unlink(missing_ok=True)


            # Удалить директории failed-задач старше FAILED_JOB_TTL_DAYS
            rows = conn.execute(
                "SELECT id FROM jobs WHERE status='failed' "
                "AND updated_at < datetime('now', ?)",
                (f"-{FAILED_JOB_TTL_DAYS} days",)
            ).fetchall()
            for row in rows:
                shutil.rmtree(get_job_dir(row["id"]), ignore_errors=True)
        finally:
            conn.close()


@asynccontextmanager
async def lifespan(app):
    init_db()


    # Восстановление зависших задач после рестарта
    conn = get_connection()
    conn.execute(
        "UPDATE jobs SET status='failed', "
        "error_message='Interrupted by server restart' "
        "WHERE status='running'"
    )
    conn.commit()
    conn.close()


    # Запуск воркера и TTL-очистки
    from backend.worker.runner import poll_loop
    worker_task = asyncio.create_task(poll_loop())
    cleanup_task = asyncio.create_task(_ttl_cleanup_loop())


    yield


    worker_task.cancel()
    cleanup_task.cancel()
    for task in (worker_task, cleanup_task):
        try:
            await task
        except asyncio.CancelledError:
            pass
```


---


#### Endpoints Specification


**Router: `/api/jobs`**


```python
# POST /api/jobs
# Создаёт задачу, возвращает job_id. НЕ запускает обработку.
# Дедупликация НЕ выполняется — повторная отправка того же URL
# создаёт новую независимую задачу.
#
# Валидация target_url (выполняется в роутере ДО создания задачи):
# import socket
# from urllib.parse import urlparse
# from backend.config import BLOCKED_IP_PREFIXES
#
# parsed = urlparse(str(target_url))
# if parsed.scheme not in ("http", "https"):
#     raise HTTPException(422, "Only http/https schemes allowed")
# try:
#     ip = socket.gethostbyname(parsed.hostname)
# except socket.gaierror:
#     raise HTTPException(422, "Cannot resolve hostname")
# if any(ip.startswith(prefix) for prefix in BLOCKED_IP_PREFIXES):
#     raise HTTPException(422, "Private/reserved IP addresses are not allowed")


Request:  JobCreateRequest(target_url: HttpUrl)
Response: JobResponse(id: int, status: str, created_at: datetime, target_url: str)
Status:   201 Created | 422 Unprocessable Entity (SSRF validation failed)
          | 429 Too Many Requests (rate limit or queue full)


# GET /api/jobs
# Список всех задач для дашборда, DESC по created_at
Request:  Query params:
            limit:  int = Query(default=20, ge=1, le=100)
            offset: int = Query(default=0, ge=0)
Response: List[JobResponse]
Status:   200 OK


# GET /api/jobs/{job_id}
# Детальный статус задачи (polling fallback)
# progress_pct: см. формулу в §2 (единственная реализация)
# Специальные случаи: status='pending' → 0; status='done' → 100
Response: JobDetailResponse(
    id, status, target_url, created_at, updated_at,
    artifact: Optional[ArtifactResponse],
    progress_pct: int
)
Status: 200 OK | 404 Not Found


# DELETE /api/jobs/{job_id}
# Псевдокод роутера:
#   job = get_job_or_404(job_id)
#   if job["status"] == "running":
#       raise HTTPException(409, "Cannot delete running job")
#   shutil.rmtree(get_job_dir(job_id), ignore_errors=True)
#   get_artifact_path(job_id).unlink(missing_ok=True)
#   conn.execute("DELETE FROM logs WHERE job_id=?", (job_id,))
#   conn.execute("DELETE FROM artifacts WHERE job_id=?", (job_id,))
#   conn.execute("DELETE FROM jobs WHERE id=?", (job_id,))
#   conn.commit()
Response: 204 No Content
Status:   204 No Content | 404 Not Found | 409 Conflict (status == 'running')
```


---


**Router: `/api/settings`**


```python
# GET /api/settings
# Возвращает все настройки.
# Ключи вида '*_api_key' — значение маскируется: возвращается '***'
Response: List[SettingResponse(key: str, value: str)]
Status:   200 OK


# PUT /api/settings
# Batch UPSERT. Использует INSERT OR REPLACE.
# Валидация значений для известных ключей выполняется перед записью (см. §4 M6)
Request:  List[SettingUpsertRequest(key: str, value: str)]
Response: {"updated": int}
Status:   200 OK
```


---


**Router: `/api/artifacts`**


```python
# GET /api/artifacts/{job_id}/download
# Псевдокод роутера:
#   job = get_job_or_404(job_id)
#   if job["status"] != "done":
#       raise HTTPException(409, "Job is not completed")
#   artifact_path = get_artifact_path(job_id)
#   if not artifact_path.exists():
#       raise HTTPException(404, "Artifact file not found on disk")
#   return FileResponse(
#       path=artifact_path,
#       media_type="application/zip",
#       filename=f"uniqueized_{job_id}_{job['created_at'][:10]}.zip"
#   )
Status: 200 OK | 404 Not Found | 409 Conflict (status != 'done')
```


---


**WebSocket: `/ws/logs/{job_id}`**


```python
# Message format (log):  {"type": "log",  "message": str, "timestamp": str, "level": str}
# Message format (term): {"type": "done", "status": str}


async def websocket_log_handler(websocket: WebSocket, job_id: int):
    from backend.state import JOB_QUEUES


    # 1. Проверить существование job → закрыть WS с кодом 4004 если нет
    job = get_job_or_none(job_id)
    if job is None:
        await websocket.close(code=4004)
        return


    await websocket.accept()


    # 2. Отправить последние 500 исторических логов
    conn = get_connection()
    rows = conn.execute(
        "SELECT message, timestamp, level FROM logs "
        "WHERE job_id=? ORDER BY timestamp ASC LIMIT 500",
        (job_id,)
    ).fetchall()
    conn.close()
    for row in rows:
        await websocket.send_json({
            "type": "log",
            "message": row["message"],
            "timestamp": row["timestamp"],
            "level": row["level"]
        })


    # 3. Если задача уже завершена — финальное сообщение и закрыть
    if job["status"] in ("done", "failed"):
        await websocket.send_json({"type": "done", "status": job["status"]})
        await websocket.close()
        return


    # 4. TOCTOU fix: воркер мог завершиться между шагом 3 и шагом 4
    queue = JOB_QUEUES.get(job_id)
    if queue is None:
        job = get_job_or_none(job_id)
        status = job["status"] if job else "failed"
        await websocket.send_json({"type": "done", "status": status})
        await websocket.close()
        return


    # 5. Цикл чтения из очереди (maxsize=1000, при переполнении дропаются старые)
    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=1.0)
                await websocket.send_json({
                    "type": "log",
                    "message": item["message"],
                    "timestamp": item["timestamp"],
                    "level": item["level"]
                })
            except asyncio.TimeoutError:
                pass


            # После каждого item или timeout — проверить статус задачи
            job = get_job_or_none(job_id)
            if job and job["status"] in ("done", "failed"):
                await websocket.send_json({"type": "done", "status": job["status"]})
                await websocket.close()
                return
    except WebSocketDisconnect:
        pass  # Клиент отключился — тихо завершить
```


---


**Секция 2 готова. Перехожу к Секции 3: §3.2–§3.4 — Database Schema, Modules 1–5, Dependencies.**


---


### 3.2 Database: SQLite Schema (финальная, единственная)


```sql
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;


CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    target_url    TEXT    NOT NULL,
    status        TEXT    NOT NULL DEFAULT 'pending',
        -- допустимые значения: 'pending' | 'running' | 'done' | 'failed'
    error_message TEXT,
    created_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);


CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at
    ON jobs (status, created_at);


CREATE TABLE IF NOT EXISTS artifacts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER NOT NULL REFERENCES jobs(id),
    file_path  TEXT    NOT NULL,
    file_size  INTEGER,
    hash       TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id)
);


CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT    NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);


INSERT OR IGNORE INTO settings (key, value) VALUES
    ('openai_api_key',              ''),
    ('anthropic_api_key',           ''),
    ('ai_provider',                 'openai'),
    ('openai_model',                'gpt-4o-mini'),
    ('anthropic_model',             'claude-3-haiku-20240307'),
        -- Верифицировать актуальность перед деплоем:
        -- GET https://api.anthropic.com/v1/models
    ('noise_intensity',             '0.01'),
    ('js_class_exclusion_prefixes', 'js-,swiper-');


-- Единственная финальная схема таблицы logs.
-- Поля module_name, marker_type, detail из предыдущих версий — удалены.
-- Маркеры прогресса пишутся в поле message (см. §2).
CREATE TABLE IF NOT EXISTS logs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id    INTEGER  NOT NULL REFERENCES jobs(id),
    level     TEXT     NOT NULL DEFAULT 'info',
        -- допустимые значения: 'info' | 'warn' | 'error'
    message   TEXT     NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);


CREATE INDEX IF NOT EXISTS idx_logs_job_id_timestamp
    ON logs (job_id, timestamp);


CREATE TRIGGER IF NOT EXISTS trg_jobs_updated_at
AFTER UPDATE ON jobs
BEGIN
    UPDATE jobs SET updated_at = datetime('now') WHERE id = NEW.id;
END;
```


---


#### `backend/database.py`


```python
import sqlite3
from pathlib import Path
from backend.config import DATABASE_URL


MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def init_db() -> None:
    conn = get_connection()
    migration_file = MIGRATIONS_DIR / "001_init.sql"
    ddl = migration_file.read_text(encoding="utf-8") \
          if migration_file.exists() else INLINE_DDL
    # executescript() неявно выполняет COMMIT перед запуском.
    # Явный conn.commit() после него избыточен и удалён.
    conn.executescript(ddl)
    conn.close()


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(
        DATABASE_URL,
        check_same_thread=False,
        timeout=10  # ожидание снятия блокировки WAL при конкурентной записи
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# Вспомогательная функция логирования для воркера и модулей.
# Каждый вызов открывает и закрывает соединение — намеренно,
# для совместимости с SQLite WAL при WORKER_CONCURRENCY > 1.
def log_message(conn: sqlite3.Connection, job_id: int,
                level: str, message: str) -> None:
    conn.execute(
        "INSERT INTO logs (job_id, level, message) VALUES (?, ?, ?)",
        (job_id, level, message)
    )
    conn.commit()


INLINE_DDL: str = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS jobs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    target_url    TEXT     NOT NULL,
    status        TEXT     NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at    DATETIME NOT NULL DEFAULT (datetime('now')),
    updated_at    DATETIME NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created_at
    ON jobs (status, created_at);
CREATE TABLE IF NOT EXISTS artifacts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id     INTEGER NOT NULL REFERENCES jobs(id),
    file_path  TEXT    NOT NULL,
    file_size  INTEGER,
    hash       TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_id)
);
CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT     NOT NULL,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO settings (key, value) VALUES
    ('openai_api_key',              ''),
    ('anthropic_api_key',           ''),
    ('ai_provider',                 'openai'),
    ('openai_model',                'gpt-4o-mini'),
    ('anthropic_model',             'claude-3-haiku-20240307'),
    ('noise_intensity',             '0.01'),
    ('js_class_exclusion_prefixes', 'js-,swiper-');
CREATE TABLE IF NOT EXISTS logs (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id    INTEGER  NOT NULL REFERENCES jobs(id),
    level     TEXT     NOT NULL DEFAULT 'info',
    message   TEXT     NOT NULL,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_logs_job_id_timestamp
    ON logs (job_id, timestamp);
CREATE TRIGGER IF NOT EXISTS trg_jobs_updated_at
AFTER UPDATE ON jobs
BEGIN
    UPDATE jobs SET updated_at = datetime('now') WHERE id = NEW.id;
END;
"""
```


---


### 3.3 Integration: Parsers & External APIs


#### Module 1: Scraper (`module_scraper.py`)


```python
# Зависимости: playwright, beautifulsoup4, lxml, httpx
# Вход:  job_id: int, target_url: str
# Выход: Path к {JOBS_WORKDIR}/{job_id}/cleaned/


from backend.config import (
    SCRAPER_PAGE_TIMEOUT_SECONDS, ASSET_DOWNLOAD_TIMEOUT_SECONDS,
    ASSET_MAX_SIZE_BYTES, MAX_PAGE_SIZE_MB, get_job_dir
)


async def scrape(job_id: int, target_url: str) -> Path:
    job_dir = get_job_dir(job_id)
    # 1. Playwright: launch chromium headless
    # 2. page.goto(url,
    #        wait_until='networkidle',
    #        timeout=SCRAPER_PAGE_TIMEOUT_SECONDS * 1000)
    # 3. page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    # 4. await page.wait_for_timeout(2000)
    # 5. html = await page.content()
    # 6. Скачиваем все src/href/srcset ресурсы через rewrite_asset_urls()
    #    httpx.AsyncClient инициализируется с:
    #      timeout=httpx.Timeout(ASSET_DOWNLOAD_TIMEOUT_SECONDS)
    # 7. Возвращаем Path к job_dir/raw/


async def clean(raw_dir: Path, job_id: int) -> Path:
    # BeautifulSoup4 + lxml
    TRACKER_DOMAINS = [
        'google-analytics.com', 'googletagmanager.com',
        'connect.facebook.net', 'pixel.facebook.com',
        'facebook.net', 'hotjar.com', 'mc.yandex.ru',
        'analytics.tiktok.com',
    ]
    FONT_DOMAINS = ['fonts.googleapis.com', 'fonts.gstatic.com']


    # Удалять: трекеры, HTML-комментарии, <bdo>/<cite>
    # Скачивать шрифты локально через download_google_fonts()


    # После rewrite_asset_urls() — обработать все скачанные CSS-файлы:
    # async with httpx.AsyncClient(
    #     timeout=httpx.Timeout(ASSET_DOWNLOAD_TIMEOUT_SECONDS)
    # ) as client:
    #     for css_file in (raw_dir / "assets").glob("*.css"):
    #         css_text = css_file.read_text(encoding="utf-8", errors="replace")
    #         css_base_url = css_origin_map.get(css_file.name, target_url)
    #         rewritten = await rewrite_css_urls(
    #             css_text, css_base_url,
    #             raw_dir / "assets", {}, client
    #         )
    #         css_file.write_text(rewritten, encoding="utf-8")
    # css_origin_map: dict[filename → original_abs_url],
    # формируется в rewrite_asset_urls() при скачивании каждого CSS.


    # Проверка суммарного размера assets:
    # total = sum(f.stat().st_size for f in (raw_dir / "assets").rglob("*") if f.is_file())
    # if total > MAX_PAGE_SIZE_MB * 1024 * 1024:
    #     raise PageSizeLimitExceeded(f"Total assets size {total} > limit")


    # Возвращаем Path к {JOBS_WORKDIR}/{job_id}/cleaned/
```


##### Обработка `srcset`


```python
async def rewrite_srcset(
    srcset_value: str,
    base_url: str,
    base_scheme: str,
    assets_dir: Path,
    cache: dict,
    client: httpx.AsyncClient,
) -> str:
    """
    Парсит srcset атрибут, заменяет каждый URL.
    Формат srcset: "url1 1x, url2 2x" или "url1 300w, url2 600w"
    """
    parts = srcset_value.split(",")
    result = []
    for part in parts:
        tokens = part.strip().split()
        if not tokens:
            continue
        url_part = tokens[0]
        descriptor = tokens[1] if len(tokens) > 1 else ""
        new_url = await _resolve_and_download_async(
            url_part, base_url, base_scheme, assets_dir, cache, client
        )
        result.append(f"{new_url} {descriptor}".strip())
    return ", ".join(result)
```


`REWRITABLE_ATTRS`:
```python
REWRITABLE_ATTRS = {'src', 'href', 'action', 'data-src', 'data-href'}
SRCSET_ATTRS     = {'srcset'}  # обрабатываются отдельно через rewrite_srcset()
```


##### Алгоритм `_resolve_and_download_async`


```python
async def _resolve_and_download_async(
    url_value: str,
    base_url: str,
    base_scheme: str,
    assets_dir: Path,
    cache: dict,
    client: httpx.AsyncClient,  # инициализирован с timeout=ASSET_DOWNLOAD_TIMEOUT_SECONDS
) -> str:
    if url_value.startswith(('data:', 'javascript:', 'mailto:', 'tel:', '#')):
        return url_value


    if url_value.startswith('//'):
        abs_url = f"{base_scheme}:{url_value}"
    elif url_value.startswith('/'):
        abs_url = urljoin(base_url, url_value)
    elif url_value.startswith(('http://', 'https://')):
        abs_url = url_value
    else:
        abs_url = urljoin(base_url, url_value)


    if abs_url in cache:
        return f"./assets/{cache[abs_url]}"


    path_part = urlparse(abs_url).path
    filename  = Path(path_part).name
    if not filename or '.' not in filename:
        filename = hashlib.md5(abs_url.encode()).hexdigest()[:8] + '.bin'


    target = assets_dir / filename
    counter = 1
    stem, suffix = Path(filename).stem, Path(filename).suffix
    while target.exists() and cache.get(abs_url) != filename:
        filename = f"{stem}_{counter}{suffix}"
        target   = assets_dir / filename
        counter += 1


    try:
        # Инкрементальное чтение чанками с per-asset лимитом
        async with client.stream("GET", abs_url) as response:
            if response.status_code != 200:
                return url_value
            chunks, total = [], 0
            async for chunk in response.aiter_bytes(chunk_size=65536):
                total += len(chunk)
                if total > ASSET_MAX_SIZE_BYTES:
                    logging.warning(
                        f"Asset too large (>{ASSET_MAX_SIZE_BYTES}B), "
                        f"skipping: {abs_url}"
                    )
                    return url_value
                chunks.append(chunk)
            target.write_bytes(b"".join(chunks))
            cache[abs_url] = filename
            return f"./assets/{filename}"
    except Exception as e:
        logging.warning(f"Asset download failed: {abs_url} → {e}")
        return url_value
```


---


#### Module 2: DOM Mutator (`module_dom_mutator.py`)


```python
# Зависимости: beautifulsoup4, lxml
# Вход:  cleaned_dir: Path, exclusion_prefixes: list[str]
# Выход: Path к {JOBS_WORKDIR}/{job_id}/mutated/
# ВАЖНО: apply_mutations() — CPU-bound, вызывать через run_in_executor


def build_selector_map(html_file: Path, css_files: list[Path],
                       exclusion_prefixes: tuple[str, ...]) -> dict[str, str]:
    """
    Источник 1 (primary):  class="", id="" атрибуты из index.html
    Источник 2 (secondary): селекторы из CSS-файлов (.class, #id)
    Объединить, дедуплицировать, пропустить exclusion_prefixes.
    Алиас: 'x' + hex(random)[2:6], пример: .order-btn → .xf9q2
    """
    selectors: set[str] = set()


    # Primary: HTML-атрибуты
    soup = BeautifulSoup(html_file.read_text(encoding="utf-8"), "lxml")
    for tag in soup.find_all(True):
        for cls in tag.get("class", []):
            selectors.add(cls)
        if tag_id := tag.get("id"):
            selectors.add(tag_id)


    # Secondary: CSS-файлы
    css_pattern = re.compile(r'(?<!["\'])([.#][\w-]+)(?=\s*[{,:\[])')
    for css_file in css_files:
        css_text = css_file.read_text(encoding="utf-8", errors="replace")
        for match in css_pattern.finditer(css_text):
            selectors.add(match.group(1).lstrip('.#'))


    selector_map = {}
    for sel in selectors:
        if any(sel.startswith(p) for p in exclusion_prefixes):
            continue
        alias = 'x' + hex(random.randint(0, 0xFFFF))[2:].zfill(4)
        selector_map[sel] = alias
    return selector_map


# В runner.py вызов через executor:
# loop = asyncio.get_event_loop()
# html_out, css_out, js_out = await loop.run_in_executor(
#     None, apply_mutations, selector_map, html_text, css_text, js_text
# )


def apply_mutations(selector_map: dict,
                    html: str, css: str, js: str) -> tuple[str, str, str]:
    # Замена в HTML class/id атрибутах
    # Замена в CSS файлах
    # Замена строковых литералов в JS по JS_REPLACE_PATTERNS
    ...


def inject_dom_noise(soup) -> None:
    # Inject hidden <div>s с alias-классами
    # CSS: .{alias} { display: none; opacity: 0; } → в <style> в <head>
    ...
```


##### Паттерны замены в JS


```python
JS_REPLACE_PATTERNS = [
    # querySelector('.class') / querySelectorAll('.class')
    r"""(querySelector(?:All)?)\(\s*(['"])\.({class_name})\2\s*\)""",
    # classList.add/remove/toggle/contains('class')
    r"""(classList\.(?:add|remove|toggle|contains))\(\s*(['"])({class_name})\2\s*\)""",
    # getElementsByClassName('class')
    r"""(getElementsByClassName)\(\s*(['"])({class_name})\2\s*\)""",
    # getElementById('id')
    r"""(getElementById)\(\s*(['"])({id_name})\2\s*\)""",
    # jQuery $('.class')
    r"""(\$\()\s*(['"])\.({class_name})\2\s*(\))""",
    # setAttribute('class', 'class-name') — только точное совпадение всего значения.
    # Известное ограничение MVP: мультиклассовые строки
    # setAttribute('class', 'foo bar old-name') НЕ обрабатываются.
    r"""(setAttribute\(\s*['"]class['"]\s*,\s*['"])({class_name})(['"])""",
]
```


---


#### Module 3: AI Rewriter (`module_ai_rewriter.py`)


```python
# Зависимости: openai>=1.50.0, anthropic>=0.34.0


SYSTEM_PROMPT = """
You are an expert direct response marketer and copywriter
specializing in traffic arbitrage.
RULES:
- Rewrite text: preserve meaning, completely change lexicon
  (Reframe, Clarify, Amplify)
- Preserve ALL HTML tags within the text fragment unchanged
- Keep output length within ±10% of input character count
- Tone: Engaging, Empathetic, Persuasive. Zero robotic clichés.
- Return ONLY the rewritten fragment, no explanations.
"""


# Узлы для рерайтинга: только если текстовый контент > 10 символов
TEXT_NODES_SELECTOR  = ['h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                         'p', 'button', 'li', 'span']
TEXT_NODE_MIN_LENGTH = 10   # символов


BATCH_SIZE           = 20
MAX_TOKENS_PER_BATCH = 3000
REWRITE_FAIL_THRESHOLD = float(os.environ.get("REWRITE_FAIL_THRESHOLD", "0.5"))
```


##### Batch-протокол (OpenAI и Anthropic)


**Формат user-сообщения (одинаков для обоих провайдеров):**
```
Rewrite each item. Return a JSON array of the same length.
Preserve the "id" field exactly. Replace only "text".


[
  {"id": 0, "text": "Buy now and save big!"},
  {"id": 1, "text": "Limited offer for new customers"}
]
```


**Ожидаемый ответ:**
```json
[
  {"id": 0, "text": "Grab yours today — exclusive savings inside."},
  {"id": 1, "text": "A special deal crafted just for first-timers"}
]
```


**Вызов OpenAI (primary):**
```python
response = await openai_client.chat.completions.create(
    model=settings["openai_model"],
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user",   "content": user_message}
    ],
    max_tokens=MAX_TOKENS_PER_BATCH,
    timeout=AI_REQUEST_TIMEOUT_SECONDS,
)
raw = response.choices[0].message.content
```


**Вызов Anthropic (fallback):**
```python
response = await anthropic_client.messages.create(
    model=settings["anthropic_model"],
    system=SYSTEM_PROMPT,
    messages=[{"role": "user", "content": user_message}],
    max_tokens=MAX_TOKENS_PER_BATCH,
)
raw = response.content[0].text
```


##### Парсинг ответа


```python
import json, re


def parse_batch_response(raw: str, original_nodes: list) -> list[str | None]:
    """
    Возвращает список переписанных текстов, сохраняя порядок original_nodes.
    None означает: использовать оригинальный текст ноды.
    """
    match = re.search(r'\[.*\]', raw, re.DOTALL)
    if not match:
        return [None] * len(original_nodes)
    try:
        items = json.loads(match.group())
    except json.JSONDecodeError:
        return [None] * len(original_nodes)


    rewritten = {
        item["id"]: item["text"]
        for item in items
        if "id" in item and "text" in item
    }
    return [rewritten.get(i) for i in range(len(original_nodes))]
```


##### Логика retry и порог отказа


```
Для каждого batch:
  1. Вызов primary (OpenAI)
  2. При HTTP 429 / 5xx / timeout → один retry на primary
  3. При повторном отказе → один вызов fallback (Anthropic)
  4. При отказе fallback → batch помечается failed,
     использовать оригинальные тексты для всех нод batch


После всех batch:
  failed_ratio = failed_batches / total_batches
  if failed_ratio > REWRITE_FAIL_THRESHOLD:
      raise ModuleFailedError(
          f"AI rewriter: {failed_ratio:.0%} batches failed"
      )
  else:
      log(job_id, 'warn',
          f"AI rewriter: {failed_ratio:.0%} batches used original text")
      # pipeline продолжается
```


---


#### Module 4: Media Uniqueizer (`module_media.py`)


```python
# Зависимости: Pillow>=10.4.0, numpy>=1.26.0


SUPPORTED_FORMATS = {'.jpg', '.jpeg', '.png', '.webp'}
# GIF, SVG — пропускать с log warn


def process_image(img_path: Path, noise_intensity: float) -> None:
    """
    Алгоритм (единственный, финальный):
    1. Открыть изображение
    2. Конвертировать в RGB (удаляет EXIF, Alpha-канал)
    3. Создать новый Image через numpy array — полная очистка метаданных
       (включая PNG tEXt/iTXt/pHYs чанки, img.info становится {})
    4. Обрезать 1px по правому и нижнему краю
    5. Добавить гауссовский шум: np.random.normal(0, noise_intensity * 255, shape)
       clamp к [0, 255], dtype=uint8
       noise_intensity берётся из settings['noise_intensity'] (default: 0.01)
       При noise_intensity=0.01: std=2.55, ~68% пикселей сдвигаются на ±3
    6. Сохранить в оригинальном формате
    """
    from PIL import Image
    import numpy as np


    img = Image.open(img_path)
    fmt = img.format  # сохранить ДО конвертации


    if fmt and fmt.upper() not in ("JPEG", "PNG", "WEBP"):
        logging.warning(f"Unsupported format {fmt}, skipping: {img_path}")
        return


    # Шаги 2–3: конвертация + очистка метаданных
    img = img.convert("RGB")
    img_array = np.array(img)
    img = Image.fromarray(img_array)
    # img.info == {} — все метаданные удалены


    # Шаг 4: crop 1px
    w, h = img.size
    if w < 2 or h < 2:
        logging.warning(f"Image too small to crop, skipping: {img_path}")
        return
    img = img.crop((0, 0, w - 1, h - 1))


    # Шаг 5: гауссовский шум
    img_array = np.array(img)
    noise = np.random.normal(0, noise_intensity * 255, img_array.shape)
    noisy = np.clip(img_array + noise, 0, 255).astype(np.uint8)
    img = Image.fromarray(noisy)


    # Шаг 6: сохранение
    # exif= не передаётся ни для одного формата — метаданные уже удалены
    if fmt and fmt.upper() == "JPEG":
        img.save(img_path, quality=92)
    elif fmt and fmt.upper() == "PNG":
        img.save(img_path, optimize=True)
    elif fmt and fmt.upper() == "WEBP":
        img.save(img_path, quality=92)
```


---


#### Module 5: Packer (`module_packer.py`)


```python
# Зависимости: zipfile, hashlib, shutil (все stdlib)
import zipfile, hashlib, shutil
from backend.config import get_job_dir, get_artifact_path, ARTIFACTS_DIR


def pack(job_id: int) -> tuple[Path, int, str]:
    rewritten_dir = get_job_dir(job_id) / "rewritten"
    output_path   = get_artifact_path(job_id)


    # Проверка свободного места перед упаковкой
    estimated_size = sum(
        f.stat().st_size
        for f in rewritten_dir.rglob("*")
        if f.is_file()
    )
    free = shutil.disk_usage(ARTIFACTS_DIR).free
    if free < estimated_size:
        raise InsufficientDiskSpaceError(
            f"Insufficient disk space: need ~{estimated_size}B, "
            f"free {free}B"
        )


    with zipfile.ZipFile(output_path, 'w',
                         compression=zipfile.ZIP_DEFLATED) as zf:
        for file in rewritten_dir.rglob("*"):
            if file.is_file():
                zf.write(file, file.relative_to(rewritten_dir))


    file_size = output_path.stat().st_size
    hash_hex  = hashlib.sha256(output_path.read_bytes()).hexdigest()
    return output_path, file_size, hash_hex


def cleanup_job_workdir(job_id: int) -> None:
    try:
        shutil.rmtree(get_job_dir(job_id), ignore_errors=True)
    except OSError as e:
        logging.warning(f"cleanup_job_workdir failed for job {job_id}: {e}")
```


---


#### WebSocket Log Broadcaster (`ws/log_broadcaster.py`)


```python
from backend.state import JOB_QUEUES


# Структура элемента очереди:
# {
#   "job_id":    int,
#   "level":     str,   # 'info' | 'warn' | 'error'
#   "message":   str,
#   "timestamp": str    # ISO 8601
# }


# Воркер (runner.py) — инициализация перед стартом пайплайна:
#   JOB_QUEUES[job_id] = asyncio.Queue(maxsize=1000)
#   При переполнении очереди: дропать самый старый элемент (FIFO).
#   Реализация:
#     try:
#         JOB_QUEUES[job_id].put_nowait(item)
#     except asyncio.QueueFull:
#         JOB_QUEUES[job_id].get_nowait()  # дроп старого
#         JOB_QUEUES[job_id].put_nowait(item)


# Каждый модуль пишет маркер как последнее действие перед return:
#   await log(job_id, 'info', 'MARKER:scraper_done')   # Module 1
#   await log(job_id, 'info', 'MARKER:mutator_done')   # Module 2
#   await log(job_id, 'info', 'MARKER:rewriter_done')  # Module 3
#   await log(job_id, 'info', 'MARKER:media_done')     # Module 4
#   await log(job_id, 'info', 'MARKER:packer_done')    # Module 5


# Воркер — после завершения пайплайна (в finally-блоке):
#   JOB_QUEUES.pop(job_id, None)
```


---


### 3.4 Dependencies Specification


**`requirements.txt` — Backend (Python 3.12)**


```
fastapi==0.115.0
uvicorn[standard]==0.30.6
pydantic==2.8.2
aiofiles==24.1.0


playwright==1.47.0
beautifulsoup4==4.12.3
lxml==5.3.0
httpx==0.27.2


openai>=1.50.0
anthropic>=0.34.0


Pillow>=10.4.0
numpy>=1.26.0


# stdlib: sqlite3, zipfile, hashlib, shutil, re, asyncio, urllib.parse, socket
```


**Frontend (`frontend/package.json`):**
`next@14`, `react@18`, `react-dom@18`, `tailwindcss@4`, `framer-motion@11`, `typescript@5`


---














## 4. Functional Requirements
> **CoT-обоснование:** Функции сгруппированы по модулям — каждый пункт
является атомарным тасков для Cursor Composer `@task`.
### M1 — Job Management
- **M1.1** `POST /api/jobs` принимает только `target_url`, валидирует URL через
Pydantic `HttpUrl`, создает запись в `jobs`, возвращает `JobResponse`
- **M1.2** Фоновая задача воркера стартует как `asyncio.Task` в FastAPI `lifespan`
(тот же OS-процесс, что и HTTP-сервер uvicorn; **не** отдельный процесс-воркер в
MVP), поллит `jobs` каждые `WORKER_POLL_INTERVAL` секунд (по умолчанию 2):
`SELECT * FROM jobs WHERE status='pending' ORDER BY created_at LIMIT 1`
- **M1.3** Worker обновляет `jobs.status` в 'running' при захвате задачи, затем в
'done' или 'failed' по завершению
- **M1.4** При любом необработанном исключении в пайплайне: `jobs.status =
'failed'`, `jobs.error_message = str(exception)`, лог с `level='error'`
- **M1.5** `DELETE /api/jobs/{job_id}`:
- **[FIX v1.5]** Если `job.status == 'running'` → вернуть `409 Conflict {"detail":
"Cannot delete a running job"}`. Удаление активной задачи запрещено.
- Если `status != 'running'` → удалить запись из `jobs`, физически удалить ZIP
(если существует) и директорию `{JOBS_WORKDIR}/{job_id}/` (если существует);
связанные записи в `logs` и `artifacts` удаляются вручную через `DELETE FROM
logs WHERE job_id=?` и `DELETE FROM artifacts WHERE job_id=?` (CASCADE
отключён)
- **[FIX v1.5]** Возвращает `204 No Content` (не `200 OK`)
- **M1.6** **[FIX v1.5] Таймаут пайплайна:** воркер оборачивает `run_pipeline()` в
`asyncio.wait_for(run_pipeline(...), timeout=JOB_TIMEOUT_SECONDS)`. При
`asyncio.TimeoutError` → `status='failed'`, `error_message=f'Pipeline timeout after
{JOB_TIMEOUT_SECONDS}s'`
### M2 — Scraper & Cleaner
- **M2.1** Playwright запускается с аргументами `--no-sandbox`,
`--disable-dev-shm-usage` (обязательно для Docker). **[FIX v1.5]** Дополнительно:
`ENV PLAYWRIGHT_BROWSERS_PATH=/app/playwright-browsers` должен быть
установлен в Dockerfile перед `RUN playwright install chromium`
- **M2.2** Timeout на `page.goto()` — 60 секунд. При превышении: `status='failed'`,
сообщение `"Target URL unreachable or timeout"`
- **M2.3** Все скачиваемые ресурсы (img, css, js, fonts) сохраняются в
`{JOBS_WORKDIR}/{job_id}/raw/assets/` через **async** `rewrite_asset_urls()`
согласно алгоритму из §3.3 (GAP-B); в CSS файлах пути заменяются через async
`rewrite_css_urls()` согласно алгоритму из §3.3 (GAP-E). **[FIX v1.5]** Ресурсы
размером > `ASSET_MAX_SIZE_BYTES` (50MB) пропускаются с log warn;
оригинальный URL сохраняется в HTML.
- **M2.4** Cleaner удаляет `<script>` теги по списку `TRACKER_DOMAINS`
- **M2.5** Cleaner удаляет `<link rel="stylesheet">` и `@import` ведущие на
`fonts.googleapis.com`; запускает `download_google_fonts()` для скачивания
шрифтов локально в `cleaned/assets/fonts/`; обновляет CSS с локальными путями
через `@font-face`
- **M2.6** Cleaner стирает все HTML-комментарии `<!-- -->`
- **M2.7** Каждое действие cleaner-а логируется в таблицу `logs` с `level='info'` и
указанием количества удаленных элементов
### M3 — DOM & CSS Mutator
- **M3.1** `build_selector_map()` парсит все `.css` файлы из `cleaned/assets/`,
строит словарь `{original_selector: new_alias}` используя regex
`re.findall(r'(?<!["\'])([.#][\w-]+)(?=\s*[{,:\[])', css_text)`
- **M3.2** Алиасы генерируются как короткие случайные строки (формат `x` + 4
hex-символа, пример: `.x8f9q`)
- **M3.3** Классы из `settings.js_class_exclusion_prefixes` (CSV) исключаются из
маппинга
- **M3.4** JS-файлы сканируются на строковые литералы по **шести паттернам**
из `JS_REPLACE_PATTERNS` (§3.3 GAP-H). Только эти шесть паттернов.
Строковая конкатенация — out of scope.
- **M3.5** DOM noise: вставка hidden `<div>` с рандомными alias-классами. **[FIX
v1.5]** Для каждого injected `<div>` генерируется dummy CSS-правило `.{alias} {
display: none; opacity: 0; }`, добавляемое в `<style>` тег в `<head>`.
- **M3.6** Randomize whitespace/переносы между тегами
### M4 — AI Text Rewriter
- **M4.1** Перед отправкой в API: проверить наличие API-ключа для активного
провайдера, иначе `status='failed'`, message `"API key not configured"`
- **M4.2** Текстовые узлы батчируются по `BATCH_SIZE=20` с ограничением
`MAX_TOKENS_PER_BATCH=3000`
- **M4.3** При API ошибке (rate limit, timeout): retry 3 раза с exponential backoff (1s,
4s, 16s), затем батч помечается как failed, используется оригинальный текст, log
warn
- **M4.4** Проверка длины: если `len(rewritten) / len(original)` выходит за пределы
`[0.85, 1.15]` — использовать оригинальный текст, логировать `warn`
- **M4.5** HTML-теги внутри текстового узла передаются в API как есть,
возвращаются без изменений
- **M4.6** Поддержка двух равнозначных провайдеров:
- `openai`: модель из `settings.openai_model` (default: `gpt-4o-mini`)
- `anthropic`: модель из `settings.anthropic_model` (default:
`claude-3-haiku-20240307`)
- Выбор через `settings.ai_provider`
- **[FIX v1.5]** Единое поле `ai_model` удалено. Каждый провайдер имеет
собственный ключ модели.
- **M4.7** **[FIX v1.5]** Если `failed_batches / total_batches >
REWRITE_FAIL_THRESHOLD (0.5)` → `status='failed'`, `error_message="AI rewrite
failed: more than 50% of batches could not be processed"`. Иначе — pipeline
продолжается с предупреждением.
### M5 — Media Uniqueizer
- **M5.1** Обрабатываются только файлы с расширениями `.jpg`, `.jpeg`, `.png`,
`.webp`
- **M5.2** EXIF stripping: `Image.open()` → конвертация в `RGB` → сохранение без
метаданных
- **M5.3** Crop: `image.crop((0, 0, width-1, height-1))` — срезается 1px
- **M5.4** Noise: `numpy.random.normal(0, noise_intensity * 255, img_array.shape)`
добавляется к массиву, `numpy.clip` к [0, 255]; `noise_intensity ≤ 0.01`
- **M5.5** SVG и GIF пропускаются, логируются как `warn: "Skipped {filename}:
format not supported"`
### M6 — Settings Management
- **M6.1** `GET /api/settings` возвращает все ключи; значения ключей содержащих
`_api_key` заменяются на `"***"` в response
- **M6.2** `PUT /api/settings` выполняет `INSERT OR REPLACE INTO settings` для
каждой пары key-value; перед записью выполняется валидация:
- `noise_intensity`: `float(value)` в диапазоне `[0.0, 0.01]`; при нарушении — HTTP
422
- `ai_provider`: значение `'openai'` или `'anthropic'`; при нарушении — HTTP 422
- `openai_model`: принимается без валидации значения
- `anthropic_model`: принимается без валидации значения
- Все остальные ключи принимаются без валидации значения
- **M6.3** Настройки хранятся в таблице `settings` (key-value); per-job параметров в
таблице `jobs` нет
### M7 — Download & Artifact
- **M7.1** `GET /api/artifacts/{job_id}/download` стримит файл через FastAPI
`FileResponse`
- **M7.2** Filename в Content-Disposition: `uniqueized_{job_id}_{created_at_date}.zip`,
где `created_at_date` берётся из поля `jobs.created_at[:10]`. [GAP-J]
- **M7.3** В `JobDetailResponse` поле `progress_pct` вычисляется по логам
модулей:
`pending=0, running/failed=COUNT(done_markers)×18, done=100`
> [ARCH-DECISION: маркеры завершения модулей в таблице `logs` — каждый
модуль после успешного завершения записывает лог-строку с `message` равным
одному из пяти константных маркеров.]
```python
# backend/worker/runner.py — константы маркеров завершения модулей
MODULE_DONE_MARKERS = {
"MODULE_SCRAPER_DONE",
"MODULE_DOM_MUTATOR_DONE",
"MODULE_AI_REWRITER_DONE",
"MODULE_MEDIA_UNIQUEIZER_DONE",
"MODULE_PACKER_DONE",
}
# SQL для вычисления progress_pct в GET /api/jobs/{job_id}:
# SELECT COUNT(*) FROM logs
# WHERE job_id = ? AND message IN (
# 'MODULE_SCRAPER_DONE', 'MODULE_DOM_MUTATOR_DONE',
# 'MODULE_AI_REWRITER_DONE', 'MODULE_MEDIA_UNIQUEIZER_DONE',
'MODULE_PACKER_DONE'
# )
# [FIX v1.5] Результат * 18 = progress_pct для статусов running И failed
# done → 100; pending → 0
```
---
## 5. UI/UX Specs
> **CoT-обоснование:** Компоненты описаны как независимые файлы с именами,
Tailwind-классами и state-логикой.
### 5.1 Design Token System (tailwind.config.ts)
```typescript
// tailwind.config.ts — использовать с Tailwind CSS v4 @theme directive
// globals.css:
@theme {
--color-bg-primary: oklch(14.5% 0.018 264); /* #0F172A Slate-950 */
--color-bg-secondary: oklch(20.5% 0.022 264); /* #1E293B Slate-800 */
--color-accent: oklch(56.9% 0.196 264); /* #3B82F6 Blue-500 */
--color-accent-hover: oklch(51.9% 0.196 264); /* #2563EB Blue-600 */
--color-text-primary: oklch(97.8% 0.004 264); /* #F8FAFC Slate-50 */
--color-text-secondary:oklch(61.5% 0.045 264); /* #94A3B8 Slate-400 */
--color-border: oklch(26% 0.025 264); /* #334155 Slate-700 */
--color-error: oklch(57.7% 0.215 27.3); /* #EF4444 Red-500 */
--color-success: oklch(64.5% 0.148 160); /* #22C55E Green-500 */
--color-warn: oklch(76.9% 0.162 70.6); /* #F59E0B Amber-400 */
--font-sans: 'Inter', system-ui, sans-serif;
--radius-card: 0.75rem; /* 12px */
}
```
### 5.2 Page Structure (Next.js App Router)
```
app/
├── layout.tsx # Root layout: bg-bg-primary, font-sans, data-theme="dark"
├── page.tsx # Dashboard (redirect to /dashboard)
├── dashboard/
│ └── page.tsx # Main view: JobInputPanel + JobList
├── jobs/
│ └── [id]/
│ └── page.tsx # Job detail: ProgressView + LogViewer
├── settings/
│ └── page.tsx # Settings form
└── not-found.tsx # 404 страница
components/
├── JobInputPanel.tsx # URL input + submit
├── JobCard.tsx # Job list item с статусом и действиями
├── JobStatusBadge.tsx # Цветной badge статуса
├── ProgressBar.tsx # Animated progress + stage label
├── LogViewer.tsx # WebSocket log stream + auto-scroll
├── SettingsForm.tsx # Key-value settings редактор
├── SkeletonCard.tsx # Skeleton loader для JobCard
└── DownloadButton.tsx # Кнопка скачивания (только если done)
```
> [ARCH-DECISION: `app/not-found.tsx` как стандартный Next.js App Router
механизм 404 — при переходе на `/jobs/999` страница `app/jobs/[id]/page.tsx`
выполняет `fetch GET /api/jobs/999`, получает 404, вызывает `notFound()` из
`next/navigation`, что рендерит `app/not-found.tsx`.]
```tsx
// app/not-found.tsx
// className контейнера: "flex flex-col items-center justify-center min-h-screen
bg-bg-primary"
// H1: "text-2xl font-semibold text-text-primary" — текст: "Page Not Found"
// P: "text-sm text-text-secondary mt-2" — текст: "The job or page you're looking for
doesn't exist."
// Link to /dashboard: className="mt-6 text-accent hover:text-accent-hover text-sm
underline"
// текст: "← Back to Dashboard"
```
### 5.3 Component Specifications
#### `<JobInputPanel />` — `/dashboard/page.tsx`
```tsx
// State: url: string, isLoading: boolean, error: string | null
// Layout: flex-col gap-6, max-w-2xl mx-auto mt-16
// URL Input:
// className="w-full bg-bg-secondary border border-border rounded-card
// px-4 py-3 text-text-primary placeholder:text-text-secondary
// focus:outline-none focus:ring-2 focus:ring-accent font-mono text-sm"
// Submit Button:
// className="w-full bg-accent hover:bg-accent-hover text-white
// font-semibold py-3 rounded-card transition-colors duration-200
// disabled:opacity-50 disabled:cursor-not-allowed"
// Text: "Uniqueize Landing" | "Processing..." (when isLoading)
// Error display:
// Показывать если error !== null, под Submit Button
// className="text-error text-sm mt-2 text-center"
// Логика:
// try {
// const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/api/jobs`, {
method: 'POST', ... })
// if (!res.ok) {
// const body = await res.json()
// setError(body.detail ?? `Error ${res.status}`)
// return
// }
// setError(null)
// const response = await res.json()
// router.push(`/jobs/${response.id}`)
// } catch (e) {
// setError("Network error, please try again")
// }
```
#### `<JobCard />` — список задач
```tsx
// className="bg-bg-secondary border border-border rounded-card p-4
// hover:border-accent/50 transition-colors duration-200 cursor-pointer"
// Layout: flex items-center justify-between
// Left section: target_url (truncated, font-mono text-sm text-text-primary)
// created_at (text-xs text-text-secondary, формат: "DD MMM, HH:mm")
// Right section: <JobStatusBadge status={job.status} />
// <DownloadButton jobId={id} /> (если done)
```
#### `<JobStatusBadge />` — маппинг статусов к цветам
```tsx
const STATUS_CONFIG = {
pending: { label: 'Queued', color: 'text-text-secondary bg-border' },
running: { label: 'Processing', color: 'text-warn bg-warn/10' },
done: { label: 'Done', color: 'text-success bg-success/10' },
failed: { label: 'Failed', color: 'text-error bg-error/10' },
}
// className="px-2 py-1 rounded-md text-xs font-medium"
```
#### `<ProgressBar />` — Job Detail Page
```tsx
// Framer Motion animated bar
// className="h-1 bg-border rounded-full overflow-hidden"
// Inner bar: motion.div с animate={{ width: `${progress_pct}%` }}
// transition={{ duration: 0.8, ease: "easeInOut" }}
// className="h-full bg-accent rounded-full"
// Stage label под баром:
// className="text-xs text-text-secondary mt-2"
// Text: "Stage: {STATUS_LABELS[status]} ({progress_pct}%)"
const STATUS_LABELS: Record<string, string> = {
pending: 'Waiting in queue',
running: 'Processing...',
done: 'Completed',
failed: 'Failed',
}
```
#### `<LogViewer />` — WebSocket Stream
```tsx
// State: logs: Array<{message: string, timestamp: string, level: string}>,
// wsStatus: 'connecting'|'connected'|'closed'
// [FIX v1.5] URL WebSocket строится из env-переменной, не хардкода:
// useEffect: new
WebSocket(`${process.env.NEXT_PUBLIC_WS_URL}/ws/logs/${jobId}`)
// Container: className="bg-bg-primary border border-border rounded-card
// p-4 h-64 overflow-y-auto font-mono text-xs"
// Each log line: className="text-text-secondary hover:text-text-primary
transition-colors py-0.5"
// [FIX v1.5] Цветовое кодирование по level из сообщения (поле level теперь
присутствует):
// level='info' → префикс timestamp: "text-accent"
// level='warn' → префикс timestamp: "text-warn"
// level='error' → префикс timestamp: "text-error"
// Auto-scroll: useRef на контейнер, scrollTop = scrollHeight при каждом новом логе
// Skeleton Loading: при wsStatus='connecting' показывать <SkeletonCard lines={5} />
// Обработка финального WebSocket-события:
// onmessage handler:
// const data = JSON.parse(event.data)
// if (data.type === 'done') {
// setWsStatus('closed')
// ws.close()
// // обновить UI в соответствии с data.status
// } else if (data.type === 'log') {
// appendLog(data.message, data.timestamp, data.level)
// }
// Polling fallback (если WS недоступен или wsStatus === 'closed' до получения
done):
// useInterval(() => fetchJob(id), 3000) — только на /jobs/[id] если job не done/failed
```
#### `<SettingsForm />` — `/settings/page.tsx`
```tsx
// State: settings: Record<string, string>, isDirty: boolean, isSaving: boolean
// useEffect: GET {NEXT_PUBLIC_API_URL}/api/settings → populate state
// On save: PUT {NEXT_PUBLIC_API_URL}/api/settings с массивом {key, value}
// Layout: flex-col gap-4, max-w-xl mx-auto mt-8
// Каждая настройка: label (text-text-secondary text-sm) + input
// API Key поля: type="password" с кнопкой показать/скрыть
// Save button: активна только если isDirty
// Success feedback: временный toast "Settings saved" (через setTimeout 2000ms)
// [FIX v1.5] Форма отображает поля openai_model и anthropic_model отдельно.
// Устаревшее поле ai_model не отображается.
```
#### `<SkeletonCard />` — Loading State
```tsx
// Использовать для JobList пока идет fetch
// className="bg-bg-secondary border border-border rounded-card p-4 animate-pulse"
// Внутри: div с bg-border/50 rounded разной ширины имитируют текст
```
### 5.4 Routing & State Management
```tsx
// State Management: React Context + useReducer (без Redux)
// JobsContext: { jobs: Job[], currentJob: Job|null, dispatch }
// Actions: ADD_JOB | UPDATE_JOB_STATUS | SET_JOBS | DELETE_JOB
// [FIX v1.5] Все API-вызовы используют process.env.NEXT_PUBLIC_API_URL:
// const API_URL = process.env.NEXT_PUBLIC_API_URL // не хардкод localhost
// const WS_URL = process.env.NEXT_PUBLIC_WS_URL
// Polling fallback (если WS недоступен):
// useInterval(() => fetchJob(id), 3000) — только на /jobs/[id] если job не done/failed
// Next.js: использовать App Router (не Pages Router)
// API calls: нативный fetch, не axios
```
### 5.5 Typography Scale
```css
/* Применять через Tailwind классы */
/* H1 Dashboard: text-2xl font-semibold text-text-primary tracking-tight */
/* H2 Section: text-lg font-medium text-text-primary */
/* Body: text-sm text-text-primary leading-relaxed */
/* Caption: text-xs text-text-secondary */
/* Mono (logs, URLs): font-mono text-xs text-text-secondary */
```
---
## 6. Error Handling — Critical Edge Cases
> **CoT-обоснование:** Перечислены как конкретные условия с точными
действиями.
### 6.1 Network & Scraping Errors
| Edge Case | Условие | Действие |
|---|---|---|
| **EC-01: URL недоступен** | `playwright TimeoutError` на `goto()` > 60s |
`status='failed'`, log error `"Timeout: target URL unreachable"`, не retry |
| **EC-02: JS-сайт без networkidle** | `page.wait_for_load_state('networkidle')` висит >
45s | Продолжить с текущим DOM, log warn `"networkidle timeout, using partial DOM"`
|
| **EC-03: Редирект на captcha** | URL в финальном `page.url` != исходный И
содержит `captcha\|verify\|challenge` | `status='failed'`, log error `"Target URL blocked
by anti-bot"` |
| **EC-04: Пустой DOM** | `len(html) < 1000` байт после scrape | `status='failed'`, log
error `"Scraped HTML too small, possible bot detection"` |
| **EC-05: Ресурс 404** | Отдельный asset возвращает HTTP != 200 при скачивании
| Пропустить ресурс, оставить оригинальный URL в HTML, log warn `"Asset
download failed: {url}"`, продолжить pipeline |
| **EC-05b: Ресурс слишком большой** | `Content-Length >
ASSET_MAX_SIZE_BYTES` (50MB) | Пропустить ресурс, оставить оригинальный
URL в HTML, log warn `"Asset too large: {url}"`, продолжить pipeline |
### 6.2 Processing Errors
| Edge Case | Условие | Действие |
|---|---|---|
| **EC-06: CSS парсинг сломан** | regex не может извлечь селекторы из
минифицированного CSS | Пропустить CSS обфускацию для этого файла, log warn
`"CSS parse failed: {filename}"` |
| **EC-07: JS-логика сломана после CSS rename** | [Невозможно гарантировать
автоматически] | Использовать exclusion_prefixes по умолчанию `js-,swiper-`.
Документировать в UI как известное ограничение |
| **EC-08: Corrupt image** | `Pillow` выбрасывает `UnidentifiedImageError` |
Пропустить файл, log warn, оригинал копируется в output без изменений |
| **EC-09: Disk full** | `OSError: No space left` при записи | `status='failed'`, log error
`"Disk space error: {str(e)}"`. Cleanup `{JOBS_WORKDIR}/{job_id}/` директории |
### 6.3 AI API Errors
| Edge Case | Условие | Действие |
|---|---|---|
| **EC-10: API Key не задан** | API-ключ активного провайдера == '' | Fail FAST до
старта Module 3, log error `"AI API key not configured. Visit /settings."` |
| **EC-11: Rate Limit (429)** | HTTP 429 от OpenAI/Anthropic | Retry 3x: backoff `[1, 4,
16]` секунд. После 3 неудач — skip batch, использовать оригинальный текст, log
warn, инкрементировать `failed_batches` |
| **EC-11b: Превышен порог неудач** | `failed_batches / total_batches > 0.5` |
`status='failed'`, `error_message="AI rewrite failed: more than 50% of batches could not
be processed"` |
| **EC-12: AI вернул невалидный HTML** | Ответ API содержит markdown-обертку (`
```html...``` `) | Strip markdown fences перед вставкой в DOM. Regex:
`r'```[\w]*\n?(.*?)```'` с `re.DOTALL` |
| **EC-13: Длина текста нарушена** | `ratio = len(rewritten) / len(original)` не в `[0.85,
1.15]` | Использовать оригинальный текст, log warn `"AI text length violated for node
{i}, using original"` |
| **EC-14: Anthropic provider недоступен** | `settings.ai_provider == 'anthropic'` но
`anthropic` не установлен | log error `"anthropic package not installed"`, `status='failed'`
|
| **EC-14b: Неверный идентификатор модели** | API возвращает `model_not_found`
| log error с указанием ключа настройки (`openai_model` или `anthropic_model`),
`status='failed'` |
### 6.4 System & Concurrency Errors
| Edge Case | Условие | Действие |
|---|---|---|
| **EC-15: Двойной захват задачи** | Два воркера подхватывают одну задачу |
`UPDATE jobs SET status='running' WHERE id=? AND status='pending'` —
атомарный UPDATE с проверкой `rowcount == 1`. Если 0 — задача уже взята,
пропустить |
| **EC-16: Контейнер перезапущен во время обработки** | После restart: задачи со
статусом `running` | При старте воркера: `UPDATE jobs SET status='failed',
error_message='Worker interrupted' WHERE status='running'`.
**[KNOWN_LIMITATION]:** resume не поддерживается в MVP. |
| **EC-17: ZIP архив уже существует** | Повторный запуск packer для done job |
**[FIX v1.5]** Использовать `INSERT OR IGNORE INTO artifacts` — атомарная
операция, исключающая дублирование. Если `changes() == 0` → запись
существует, вернуть существующий path. |
| **EC-18: WebSocket disconnect** | Клиент закрыл браузер во время стриминга
логов | `try/except WebSocketDisconnect` — тихо закрыть соединение, не
прерывать воркер |
| **EC-19: Pipeline timeout** | `asyncio.wait_for(run_pipeline(...),
JOB_TIMEOUT_SECONDS)` истёк | `status='failed'`, `error_message=f'Pipeline
timeout after {JOB_TIMEOUT_SECONDS}s'` |
### 6.5 Validation Errors (FastAPI)
```python
# Все Pydantic ValidationError автоматически возвращают 422
# Дополнительные кастомные валидации:
# POST /api/jobs:
# - URL не начинается с http:// или https:// → 400 "URL must start with http:// or
https://"
# - Повторная отправка того же target_url: разрешена (GAP-I). Новая задача
создаётся.
# PUT /api/settings:
# - key='noise_intensity', float(value) не в [0.0, 0.01] → 422
# - key='ai_provider', value не в {'openai', 'anthropic'} → 422
# DELETE /api/jobs/{job_id}:
# [FIX v1.5] - job.status == 'running' → 409 {"detail": "Cannot delete a running job"}
# GET /api/artifacts/{job_id}/download:
# - job.status != 'done' → 409 {"detail": "Job not completed", "current_status": str}
# - Файл не найден на диске (artifacts.file_path) → 500 {"detail": "Artifact file missing
from disk"}
```
---
## 7. Infrastructure Specification
### 7.1 Dockerfile
> [ARCH-DECISION: однослойный Dockerfile с python:3.12-slim как базовым
образом; Node.js устанавливается через apt-get; `entrypoint.sh` запускает `uvicorn`
и `next start` через `&` с `wait`, без supervisord; playwright устанавливается с
chromium через `playwright install --with-deps chromium`;
`PLAYWRIGHT_BROWSERS_PATH` явно задаётся для корректной работы от root и
при смене user; директория `migrations/` обязательно копируется в образ.]
```dockerfile
# Dockerfile
FROM python:3.12-slim AS base
# [FIX v1.5] Явная установка PLAYWRIGHT_BROWSERS_PATH перед установкой
браузера
# Гарантирует корректный путь независимо от USER директивы
ENV PLAYWRIGHT_BROWSERS_PATH=/app/playwright-browsers
# Системные зависимости для Playwright Chromium, Pillow и Node.js
RUN apt-get update && apt-get install -y --no-install-recommends \
libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
libdbus-1-3 libxcb1 libxkbcommon0 libx11-6 libxcomposite1 libxdamage1 \
libxext6 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 libcairo2 \
libasound2 libatspi2.0-0 \
nodejs npm curl \
&& rm -rf /var/lib/apt/lists/*
WORKDIR /app
# --- Backend: Python зависимости ---
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
# [FIX v1.5] playwright install использует PLAYWRIGHT_BROWSERS_PATH из ENV
RUN playwright install --with-deps chromium
# --- Frontend: Node зависимости ---
COPY frontend/package.json frontend/package-lock.json ./frontend/
RUN cd frontend && npm ci --production=false
# --- Frontend: сборка с подстановкой build-time env ---
# [FIX v1.5] NEXT_PUBLIC_* переменные встраиваются в JS-бандл на этапе
сборки.
# Для production деплоя необходимо передать реальные значения через
--build-arg:
# docker build --build-arg NEXT_PUBLIC_API_URL=http://1.2.3.4:8000 \
# --build-arg NEXT_PUBLIC_WS_URL=ws://1.2.3.4:8000 .
# Дефолтные значения для локальной разработки:
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL}
COPY frontend/ ./frontend/
RUN cd frontend && npm run build
# --- Копирование исходного кода ---
COPY backend/ ./backend/
# [GAP-A] migrations/ ОБЯЗАТЕЛЬНО копируется в образ — содержит 001_init.sql
COPY migrations/ ./migrations/
COPY entrypoint.sh ./entrypoint.sh
RUN chmod +x ./entrypoint.sh
# Создание директорий для данных
RUN mkdir -p /app/data /app/volumes/artifacts /app/volumes/jobs \
/app/playwright-browsers
EXPOSE 8000 3000
CMD ["./entrypoint.sh"]
```
### 7.2 entrypoint.sh
```bash
#!/bin/bash
# entrypoint.sh
# [ARCH-DECISION: bash + & + wait вместо supervisord — нативный bash, нулевые
зависимости]
set -e
echo "[entrypoint] Starting AI Landing Page Uniqueizer..."
# Запуск FastAPI backend
cd /app
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!
echo "[entrypoint] Backend started (PID: $BACKEND_PID)"
# Запуск Next.js frontend
cd /app/frontend
npm run start -- --port 3000 --hostname 0.0.0.0 &
FRONTEND_PID=$!
echo "[entrypoint] Frontend started (PID: $FRONTEND_PID)"
# Обработка сигналов завершения
trap "echo '[entrypoint] Shutting down...'; kill $BACKEND_PID $FRONTEND_PID
2>/dev/null; exit 0" SIGTERM SIGINT
# Ожидать завершения любого процесса
wait -n $BACKEND_PID $FRONTEND_PID
EXIT_CODE=$?
echo "[entrypoint] One process exited with code $EXIT_CODE. Stopping all..."
kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
exit $EXIT_CODE
```
### 7.3 CORS Configuration (main.py)
> [ARCH-DECISION: FastAPI CORSMiddleware с явным `allow_origins` — для
self-hosted продукта origin предсказуем; запрещён wildcard `"*"`. **[FIX v1.5]**
`allow_origins` читается из env-переменной `CORS_ORIGINS` (CSV), что позволяет
задать production origin без пересборки образа.]
```python
# backend/main.py — CORS configuration
import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio
JOB_QUEUES: dict[int, asyncio.Queue] = {}
app = FastAPI(title="AI Landing Page Uniqueizer")
# [FIX v1.5] allow_origins из env-переменной CORS_ORIGINS (CSV)
# Default для локальной разработки: localhost:3000 и 127.0.0.1:3000
_cors_origins_raw = os.environ.get(
"CORS_ORIGINS",
"http://localhost:3000,http://127.0.0.1:3000"
)
_allow_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]
app.add_middleware(
CORSMiddleware,
allow_origins=_allow_origins,
allow_credentials=True,
allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
allow_headers=["Content-Type", "Authorization"],
)
```
### 7.4 Docker Compose (docker-compose.yml)
```yaml
version: '3.9'
services:
app:
build:
context: .
# [FIX v1.5] Build-time аргументы для NEXT_PUBLIC_* переменных.
# При production деплое: создать .env и раскомментировать args.
# args:
# NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL}
# NEXT_PUBLIC_WS_URL: ${NEXT_PUBLIC_WS_URL}
ports:
- "8000:8000" # FastAPI backend
- "3000:3000" # Next.js frontend
volumes:
- sqlite_data:/app/data # SQLite database file
- artifacts_data:/app/volumes/artifacts # ZIP archives
# ПРИМЕЧАНИЕ: /app/volumes/jobs (JOBS_WORKDIR) намеренно НЕ
монтируется
# как именованный volume — промежуточные файлы задач являются
эфемерными
# и удаляются после упаковки (module_packer.cleanup_job_workdir).
# При перезапуске контейнера незавершённые задачи получают status='failed'
# через EC-16 (reset running → failed при старте воркера).
environment:
- DATABASE_URL=/app/data/app.db
- ARTIFACTS_DIR=/app/volumes/artifacts
- JOBS_WORKDIR=/app/volumes/jobs
- WORKER_POLL_INTERVAL=2
- JOB_TIMEOUT_SECONDS=600
- ASSET_MAX_SIZE_BYTES=52428800 # 50MB
# [FIX v1.5] CORS_ORIGINS задаётся для production:
# - CORS_ORIGINS=http://your-server-ip:3000
restart: unless-stopped
volumes:
sqlite_data:
artifacts_data:
```
### 7.5 Environment Variables (полный список)
```env
# ===== BACKEND =====
DATABASE_URL=/app/data/app.db
ARTIFACTS_DIR=/app/volumes/artifacts
JOBS_WORKDIR=/app/volumes/jobs
WORKER_POLL_INTERVAL=2 # секунды между поллингами БД
JOB_TIMEOUT_SECONDS=600 # [FIX v1.5] таймаут всего пайплайна в
секундах
ASSET_MAX_SIZE_BYTES=52428800 # [FIX v1.5] 50MB — лимит размера
скачиваемого ассета
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000 # [FIX v1.5] CSV
# ===== FRONTEND (build-time — встраиваются в JS-бандл при npm run build)
=====
# [FIX v1.5] Передаются через docker build --build-arg или .env перед сборкой
NEXT_PUBLIC_API_URL=http://localhost:8000 # заменить на публичный IP/домен
при VPS-деплое
NEXT_PUBLIC_WS_URL=ws://localhost:8000 # заменить на публичный IP/домен
при VPS-деплое
```
### 7.6 Startup Sequence (main.py lifespan)
```python
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from backend.database import init_db
from backend.worker.runner import worker_loop
from backend.config import JOBS_WORKDIR, ARTIFACTS_DIR
JOB_QUEUES: dict[int, asyncio.Queue] = {}
@asynccontextmanager
async def lifespan(app: FastAPI):
# 1. Создать необходимые директории если не существуют
JOBS_WORKDIR.mkdir(parents=True, exist_ok=True)
ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
# 2. Инициализировать БД
init_db()
# 3. EC-16: reset interrupted jobs (status='running' → 'failed')
from backend.database import get_connection
conn = get_connection()
conn.execute(
"UPDATE jobs SET status='failed', error_message='Worker interrupted' WHERE
status='running'"
)
conn.commit()
conn.close()
# 4. Запустить worker loop как asyncio.Task
worker_task = asyncio.create_task(worker_loop())
yield
# Shutdown: отменить worker task
worker_task.cancel()
try:
await worker_task
except asyncio.CancelledError:
pass
app = FastAPI(title="AI Landing Page Uniqueizer", lifespan=lifespan)
```
```python
# backend/worker/runner.py — механизм доступа к JOB_QUEUES (GAP-D)
from backend.main import JOB_QUEUES
from backend.config import WORKER_POLL_INTERVAL, JOB_TIMEOUT_SECONDS
async def worker_loop() -> None:
"""Основной цикл воркера. Поллит БД каждые WORKER_POLL_INTERVAL
секунд."""
while True:
try:
job = claim_next_pending_job() # атомарный UPDATE + SELECT
if job:
job_id = job["id"]
JOB_QUEUES[job_id] = asyncio.Queue()
try:
# [FIX v1.5] Таймаут всего пайплайна
await asyncio.wait_for(
run_pipeline(job_id, job["target_url"]),
timeout=JOB_TIMEOUT_SECONDS
)
except asyncio.TimeoutError:
_mark_failed(job_id, f"Pipeline timeout after
{JOB_TIMEOUT_SECONDS}s")
finally:
JOB_QUEUES.pop(job_id, None)
else:
await asyncio.sleep(WORKER_POLL_INTERVAL)
except asyncio.CancelledError:
raise
except Exception as e:
import logging
logging.error(f"Worker loop unexpected error: {e}")
await asyncio.sleep(WORKER_POLL_INTERVAL)
```
### 7.7 Production Deployment (GAP-L)
[ARCH-DECISION: **[FIX v1.5]** `NEXT_PUBLIC_*` переменные встраиваются в
JS-бандл на этапе `npm run build` (build-time, не runtime). Для production деплоя
необходимо передать реальные значения ДО сборки образа через `--build-arg`.
`.env.example` содержит инструкцию по правильной процедуре.]
```bash
# .env.example — скопируйте в .env и замените значения перед деплоем
# ===== BACKEND =====
DATABASE_URL=/app/data/app.db
ARTIFACTS_DIR=/app/volumes/artifacts
JOBS_WORKDIR=/app/volumes/jobs
WORKER_POLL_INTERVAL=2
JOB_TIMEOUT_SECONDS=600
ASSET_MAX_SIZE_BYTES=52428800
# ===== FRONTEND (ВАЖНО: build-time переменные) =====
# [FIX v1.5] Эти переменные встраиваются в JS-бандл при сборке образа.
# Необходимо передавать через --build-arg при docker build.
# При деплое на VPS замените localhost на публичный IP или домен:
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
# ===== CORS =====
# Список разрешённых origins для CORS (CSV), читается backend'ом в runtime:
CORS_ORIGINS=http://localhost:3000
```
```yaml
# docker-compose.yml — production версия с build-args
version: '3.9'
services:
app:
build:
context: .
args:
# [FIX v1.5] Значения читаются из .env файла через env_file
NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL}
NEXT_PUBLIC_WS_URL: ${NEXT_PUBLIC_WS_URL}
env_file:
- .env
ports:
- "8000:8000"
- "3000:3000"
volumes:
- sqlite_data:/app/data
- artifacts_data:/app/volumes/artifacts
restart: unless-stopped
volumes:
sqlite_data:
artifacts_data:
```
> **Инструкция по VPS-деплою (шаги):**
> 1. `git clone <repo> && cd <repo>`
> 2. `cp .env.example .env`
> 3. Открыть `.env` и заменить `localhost` на публичный IP или домен сервера в
`NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL` и `CORS_ORIGINS`
> 4. `docker-compose up -d --build`
> *(build-args автоматически подхватываются из .env через env_file + args)*
> 5. Открыть `http://<your-ip>:3000` в браузере
> 6. Перейти в Settings и ввести API-ключ для OpenAI или Anthropic
---
## 8. Out of Scope (MVP)
Следующее НЕ реализуется в MVP и помечено как `[FUTURE]` или
`[KNOWN_LIMITATION]`:
- `[FUTURE]` Аутентификация / multi-user
- `[FUTURE]` Очередь из нескольких параллельных воркеров (Celery/ARQ)
- `[FUTURE]` Поддержка SPA-лендингов с динамической навигацией (router-based)
- `[FUTURE]` Кастомные промпты пользователя для AI модуля
- `[FUTURE]` Защита кода (Nuitka/PyArmor) — применяется при финальной сборке,
не в dev
- `[FUTURE]` Preview уникализированного лендинга в iframe перед скачиванием
- `[FUTURE]` Уровни агрессивности обфускации (aggression_level) как per-job
параметр
- `[FUTURE]` Per-job asyncio.Queue уже реализована в v1.5; при multi-worker
заменить на pub/sub (Redis)
- `[KNOWN_LIMITATION]` **Многостраничные лендинги (GAP-G):** Pipeline
обрабатывает только `index.html`. Вторичные HTML-страницы (`/thank-you.html`,
`/privacy.html` и т.д.) включаются в ZIP без обработки как статические файлы.
- `[KNOWN_LIMITATION]` **Resume при сбое пайплайна (GAP-M):** При сбое
контейнера между модулями весь прогресс теряется. EC-16 сбрасывает задачу в
`status='failed'`. Пользователь должен создать новую задачу.
- `[KNOWN_LIMITATION]` **Строковая конкатенация в JS:** Замена CSS-классов в
JS-коде, использующем строковую конкатенацию (`'class-' + varName`), не
поддерживается — требует AST-парсера. Покрываются только шесть явных
паттернов из `JS_REPLACE_PATTERNS`.
- `[KNOWN_LIMITATION]` **Внешние ассеты в ZIP:** При недоступности ассета во
время скачивания оригинальный внешний URL сохраняется в HTML. ZIP может
содержать ссылки на внешние CDN, что является следом (footprint). Мониторинг
таких случаев через log warn.
---
*Документ финализирован v1.5. Версия для Cursor: использовать как
единственный источник при генерации кода. При противоречии между разделами
— приоритет: Section 3 > Section 4 > Section 2.*