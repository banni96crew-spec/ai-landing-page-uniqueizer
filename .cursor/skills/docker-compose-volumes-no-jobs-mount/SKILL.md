```markdown
---
name: docker-compose-volumes-no-jobs-mount
description: Enforces docker-compose.yml configuration with exactly two named volumes (sqlite_data and artifacts_data), no mount for /app/volumes/jobs, and proper .env.example guidance for VPS deployment. Use when editing docker-compose.yml or environment configuration in DevOps / Docker.
---
# docker-compose-volumes-no-jobs-mount

## When to use
Use this skill when working on:

- `docker-compose.yml`
- Volume configuration
- Environment configuration
- `.env` / `.env.example`
- VPS deployment setup

Applies only to **AI Landing Page Uniqueizer** infrastructure.

---

## Rationale from PRD

§7.4, GAP-L:

- Exactly two named volumes:
  - `sqlite_data:/app/data`
  - `artifacts_data:/app/volumes/artifacts`
- `/app/volumes/jobs` MUST NOT be mounted
  - Intermediate files are ephemeral
  - Deleted by Module 5 packer
- `.env.example` must include:
  - Comment explaining localhost → public IP/domain replacement for VPS
- Use:
  ```yaml
  env_file:
    - .env
  ```
  for production config

---

## Required instruction

In `docker-compose.yml`:

- Mount only:
  - `sqlite_data:/app/data`
  - `artifacts_data:/app/volumes/artifacts`
- Do NOT add volume for:
  ```
  /app/volumes/jobs
  ```
- Provide `.env.example` with comments explaining:
  - Replace `localhost` with public IP/domain on VPS
- Use:
  ```yaml
  env_file:
    - .env
  ```

---

## Non-negotiable rules

1. Exactly one service: `app`.
2. Exactly two named volumes.
3. No volume for `/app/volumes/jobs`.
4. `/app/volumes/jobs` must remain ephemeral.
5. Use `restart: unless-stopped`.
6. Use `.env` via `env_file`.
7. `.env.example` must contain deployment guidance.
8. Do not mount project source in production.
9. Do not add extra volumes.

---

# Required docker-compose.yml structure

```yaml
version: "3.9"

services:
  app:
    build:
      context: .
      args:
        # [FIX v1.5] NEXT_PUBLIC_* are embedded into the JS bundle at build-time.
        # Values are read from .env via env_file + args. Must be set before docker build.
        NEXT_PUBLIC_API_URL: ${NEXT_PUBLIC_API_URL}
        NEXT_PUBLIC_WS_URL: ${NEXT_PUBLIC_WS_URL}
    container_name: ai-landing-page-uniqueizer
    ports:
      - "8000:8000"
      - "3000:3000"
    volumes:
      - sqlite_data:/app/data
      - artifacts_data:/app/volumes/artifacts
    env_file:
      - .env
    restart: unless-stopped

volumes:
  sqlite_data:
  artifacts_data:
```

---

## Critical rule

❌ DO NOT add:

```yaml
- /app/volumes/jobs
```

Reason:

- `jobs/` contains:
  - raw/
  - cleaned/
  - mutated/
  - rewritten/
- Deleted by packer (`shutil.rmtree`)
- Must remain ephemeral

---

# Required .env.example

```env
# ============================================================
# AI Landing Page Uniqueizer — Environment Configuration
# ============================================================
# Copy to .env and fill in values before deploying.

# ===== BACKEND =====
DATABASE_URL=/app/data/app.db
ARTIFACTS_DIR=/app/volumes/artifacts
JOBS_WORKDIR=/app/volumes/jobs
WORKER_POLL_INTERVAL=2
JOB_TIMEOUT_SECONDS=600
ASSET_MAX_SIZE_BYTES=52428800

# ===== FRONTEND (IMPORTANT: build-time variables) =====
# These are embedded into the JS bundle at image build time (npm run build).
# Must be passed via --build-arg at docker build (handled automatically via env_file + args).
# For local development:
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000

# ===== CORS =====
# Allowed origins for CORS (CSV), read by the backend at runtime.
# For local development:
CORS_ORIGINS=http://localhost:3000

# ============================================================
# VPS / Production Deployment Instructions
# ============================================================
# When deploying to a VPS or cloud server, replace "localhost"
# with your public IP address or domain name in ALL three variables:
#
# NEXT_PUBLIC_API_URL=http://123.45.67.89:8000
# NEXT_PUBLIC_WS_URL=ws://123.45.67.89:8000
# CORS_ORIGINS=http://123.45.67.89:3000
#
# Or with domain:
# NEXT_PUBLIC_API_URL=https://yourdomain.com
# NEXT_PUBLIC_WS_URL=wss://yourdomain.com
# CORS_ORIGINS=https://yourdomain.com
```

Must clearly explain:

- localhost replacement in `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_WS_URL`, **and `CORS_ORIGINS`**
- IP or domain usage
- That `NEXT_PUBLIC_*` are build-time variables requiring `--build-arg`

---

# Correct architecture

Persistent:

```
/app/data                → sqlite_data (named volume)
/app/volumes/artifacts   → artifacts_data (named volume)
```

Ephemeral:

```
/app/volumes/jobs        → NOT mounted
```

---

# Prohibited patterns

- ❌ Mounting `/app/volumes/jobs`
- ❌ Adding third volume
- ❌ Using bind mount in production
- ❌ Omitting `env_file`
- ❌ Hardcoding production URLs in compose file
- ❌ Using `restart: always`
- ❌ Splitting frontend/backend into separate services
- ❌ Removing named volumes block

---

# Definition of done

- docker-compose has exactly 1 service (`app`)
- Exactly 2 named volumes declared
- `/app/volumes/jobs` not mounted
- `build.args` includes `NEXT_PUBLIC_API_URL` and `NEXT_PUBLIC_WS_URL`
- `env_file: - .env` configured
- `restart: unless-stopped` present
- `.env.example` exists with all required variables (including `CORS_ORIGINS` and backend vars)
- `.env.example` explains localhost → public IP/domain replacement for `NEXT_PUBLIC_*` **and** `CORS_ORIGINS`
- Fully compliant with PRD §7.4, §7.7 and GAP-L
```