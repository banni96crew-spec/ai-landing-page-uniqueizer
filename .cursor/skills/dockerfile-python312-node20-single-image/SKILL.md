```markdown
---
name: dockerfile-python312-node20-single-image
description: Enforces single-image Dockerfile using python:3.12-slim with Node.js installed via apt-get, Playwright Chromium with --with-deps, required COPY migrations/, and entrypoint.sh without supervisord. Use when editing Dockerfile or container build logic in DevOps / Docker.
---
# dockerfile-python312-node20-single-image

## When to use
Use this skill when working on:

- `Dockerfile`
- Container build configuration
- Runtime packaging
- Playwright installation
- Node/Next.js build integration
- GAP-A compliance

Applies only to **AI Landing Page Uniqueizer** infrastructure.

---

## Rationale from PRD

§7.1:

- Single image
- Base image: `python:3.12-slim`
- Node.js + npm installed via `apt-get`
- Playwright:
  ```
  playwright install --with-deps chromium
  ```
- Must include:
  ```
  COPY migrations/ ./migrations/
  ```
- Build Next.js inside container
- `entrypoint.sh` must use bash & wait
- No supervisord
- No multi-stage split runtime

---

## Required instruction

- Base:
  ```dockerfile
  FROM python:3.12-slim
  ```
- Install nodejs/npm via apt-get.
- Run:
  ```
  playwright install --with-deps chromium
  ```
  after pip install.
- Always include:
  ```
  COPY migrations/ ./migrations/
  ```
- Build Next.js:
  ```dockerfile
  RUN cd frontend && npm ci --production=false && npm run build
  ```
- CMD:
  ```dockerfile
  CMD ["./entrypoint.sh"]
  ```
- No supervisord.
- No multi-stage build splitting runtimes.

---

## Non-negotiable rules

1. Must use `python:3.12-slim`.
2. Must set `ENV PLAYWRIGHT_BROWSERS_PATH=/app/playwright-browsers` immediately after `FROM`.
3. Must install Node via apt-get.
4. Must not use separate node image stage.
5. Must run Playwright install with `--with-deps chromium`.
6. Must copy requirements from `backend/requirements.txt`, not project root.
7. Must declare `ARG NEXT_PUBLIC_API_URL` + `ARG NEXT_PUBLIC_WS_URL` and promote to `ENV` **before** `npm run build`.
8. Must include `COPY migrations/ ./migrations/`.
9. Must create required directories.
10. Must expose ports 8000 and 3000.
11. Must use `entrypoint.sh`.
12. Must not use supervisord.
13. Must not split backend/frontend into separate runtime images.

---

# Required Dockerfile structure

## Base image

```dockerfile
FROM python:3.12-slim
# [FIX v1.5] Must be set before playwright install — guarantees correct
# browser path regardless of USER directive
ENV PLAYWRIGHT_BROWSERS_PATH=/app/playwright-browsers
```

No alpine.
No multi-stage.

---

## System dependencies

```dockerfile
RUN apt-get update && apt-get install -y \
    nodejs \
    npm \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*
```

Node must come from apt.

---

## Workdir

```dockerfile
WORKDIR /app
```

---

## Python dependencies

```dockerfile
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
```

---

## Playwright install (required)

After pip install:

```dockerfile
RUN playwright install --with-deps chromium
```

Must include:
```
--with-deps chromium
```

Not:
```
playwright install
```

---

## Copy application code

```dockerfile
COPY backend/ ./backend/
COPY frontend/ ./frontend/
COPY entrypoint.sh ./entrypoint.sh
COPY migrations/ ./migrations/
```

`COPY migrations/ ./migrations/` is mandatory (GAP-A).

---

## Create required directories

```dockerfile
RUN mkdir -p /app/data \
    /app/volumes/artifacts \
    /app/volumes/jobs
```

Must match PRD paths.

---

## Build Next.js

```dockerfile
# [FIX v1.5] NEXT_PUBLIC_* are embedded into the JS bundle at build time.
# ARG/ENV must be declared BEFORE npm run build so --build-arg values
# are available to the Next.js compiler.
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ARG NEXT_PUBLIC_WS_URL=ws://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}
ENV NEXT_PUBLIC_WS_URL=${NEXT_PUBLIC_WS_URL}

RUN cd frontend && \
    npm ci --production=false && \
    npm run build
```

Must:

- Use `npm ci`
- Not skip build
- Not rely on dev server build at runtime

---

## Expose ports

```dockerfile
EXPOSE 8000 3000
```

---

## Entrypoint

```dockerfile
RUN chmod +x entrypoint.sh
CMD ["./entrypoint.sh"]
```

Must not use:

- supervisord
- pm2
- docker-compose override

---

# entrypoint.sh requirements

Must:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port 8000 &
cd /app/frontend && npm run start -- --port 3000 --hostname 0.0.0.0 &
wait -n
```

Must:

- Use bash
- Use `&`
- Use `wait`
- Handle SIGTERM/SIGINT
- Not use supervisord

---

# Prohibited patterns

- ❌ Multi-stage split (separate runtime images)
- ❌ Using node:20 base stage
- ❌ Using alpine
- ❌ Omitting migrations copy
- ❌ Omitting Playwright --with-deps
- ❌ Using supervisord
- ❌ Using pm2
- ❌ Running Next.js in dev mode
- ❌ Splitting frontend/backend into separate containers
- ❌ Using gunicorn instead of uvicorn

---

# Definition of done

- Base image: `python:3.12-slim`
- `ENV PLAYWRIGHT_BROWSERS_PATH=/app/playwright-browsers` set before apt-get
- Node/npm installed via apt-get
- Playwright installed with `--with-deps chromium`
- `requirements.txt` copied from `backend/requirements.txt`
- `ARG`/`ENV` for `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL` declared before `npm run build`
- `COPY migrations/ ./migrations/` present
- Next.js built via `npm ci && npm run build`
- Ports 8000 and 3000 exposed
- `CMD ["./entrypoint.sh"]`
- No supervisord
- Single unified image
- Fully compliant with PRD §7.1 and GAP-A
```