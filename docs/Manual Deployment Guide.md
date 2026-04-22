# Manual Deployment Guide for AI Landing Page Uniqueizer (MVP) on a VPS

> Stack strictly complies with PRD v1.5:
> **Backend:** FastAPI + Uvicorn, SQLite (WAL), Playwright (Chromium), OpenAI / Anthropic, Pillow, NumPy
> **Frontend:** Next.js 14 (App Router), React 18, Tailwind v4
> **Infrastructure:** Docker, Docker Compose, python:3.12-slim
> **Orchestration:** one container (backend + frontend via entrypoint.sh)

---

# 1️Server Preparation

## 1.1 System Update

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg lsb-release git
```

### Why is this important
Updates fix vulnerabilities. Git is required to clone the repository.

---

## 1.2 Installing Docker (current method 2025–2026)

Removing old versions:

```bash
sudo apt remove -y docker docker-engine docker.io containerd runc
```

Adding the official Docker repository:

```bash
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | \ 
sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo\ 
"deb [arch=$(dpkg --print-architecture) \ 
signed-by=/etc/apt/keyrings/docker.gpg] \ 
https://download.docker.com/linux/ubuntu\ 
$(lsb_release -cs) stable" | \
sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
```

Install Docker Engine + Compose plugin:

```bash
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io \
docker-buildx-plugin docker-compose-plugin
```

Check:

```bash
docker --version
docker compose version
```

Add user to docker group:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

### Why this is important
- Uses the modern `docker compose` command
- Compose plugin is required for production configurations from PRD
- Playwright requires a full Docker Engine (not rootless)

---

# 2️ Cloning the repository and access rights

## 2.1 Cloning a Project

```bash
git clone <YOUR_REPOSITORY_URL>
cd <PROJECT_FOLDER>
```

If you're using a private repository, set up an SSH key:

```bash
ssh-keygen -t ed25519 -C "vps-deploy"
cat ~/.ssh/id_ed25519.pub
```

Add the key to your Git provider.

---

## 2.2 Checking the structure

The project root should contain:

```
backend/
frontend/
migrations/
Dockerfile
docker-compose.yml
entrypoint.sh
.env.example
```

---

## 2.3 Directory permissions

```bash
sudo chown -R $USER:$USER .
chmod +x entrypoint.sh
```

### Why this is important
- entrypoint.sh must be executable
- Docker build uses the local context – permissions are important

---

# 3️ Environment Configuration (.env)

Create a file:

```bash
cp .env.example .env
```

Open:

```bash
nano .env
```

---

## 3.1 Backend Variables (runtime)

```env
DATABASE_URL=/app/data/app.db
ARTIFACTS_DIR=/app/volumes/artifacts
JOBS_WORKDIR=/app/volumes/jobs

WORKER_POLL_INTERVAL=2
JOB_TIMEOUT_SECONDS=600
ASSET_MAX_SIZE_BYTES=52428800

CORS_ORIGINS=http://YOUR_SERVER_IP:3000
``

### What to change:
- `YOUR_SERVER_IP` → public IP or VPS domain
- If using a domain → specify https://yourdomain.com

---

## 3.2 Frontend variables (build-time!)

⚠️ IMPORTANT: NEXT_PUBLIC_* variables are embedded in the JS bundle during the Docker image build phase.

```env
NEXT_PUBLIC_API_URL=http://YOUR_SERVER_IP:8000
NEXT_PUBLIC_WS_URL=ws://YOUR_SERVER_IP:8000
``

If using HTTPS + reverse proxy:

```env
NEXT_PUBLIC_API_URL=https://yourdomain.com
NEXT_PUBLIC_WS_URL=wss://yourdomain.com
```

---

## 3.3 Final Check

Check:

- CORS_ORIGINS matches the frontend URL
- NEXT_PUBLIC_API_URL points to the backend
- NEXT_PUBLIC_WS_URL uses ws:// or wss://

### Why this is important
- Incorrect NEXT_PUBLIC_* → the frontend will access localhost
- Invalid CORS → 403 errors
- WebSocket won't connect if scheme is invalid (ws/wss)

---

# 4️ Building and Running

## 4.1 Production Build

```bash
docker compose up -d --build
```

What will happen:

1. Python 3.12 will be installed
2. Backend dependencies (FastAPI, Playwright, Pillow, etc.) will be installed
3. `playwright install --with-deps chromium` will be run
4. Node.js will be installed
5. `npm run build` will be run
6. Backend and Frontend will be started via entrypoint.sh

---

## 4.2 Container Checking

```bash
docker compose ps
```

Expected:

```
app running
```

---

# 5️ Verifying Operation

## 5.1 Checking Logs

```bash
docker compose logs -f
```

Looking for:

```
Backend started (PID: ...)
Frontend started (PID: ...)
```

---

## 5.2 Checking API

```bash
curl http://YOUR_SERVER_IP:8000/docs
```

Expecting Swagger UI.

---

## 5.3 Checking the Frontend

Open in a browser:

```
http://YOUR_SERVER_IP:3000
```

---

## 5.4 Checking Volume Data

```bash
docker volume ls
```

Should be:

```
sqlite_data
artifacts_data
```

---

## 5.5 Checking the SQLite Database Inside the Container

```bash
docker exec -it <container_name> bash
ls /app/data
```

The file should appear after the first run.

---

# ✅ Full Check Cycle

1. Open `/settings`
2. Enter `openai_ap`i_key` or `anthropic_api_key`
3. Create a task
4. Check:
- WebSocket log is streaming
- Status is changing
- ZIP is downloading

---

# Troubleshooting

## ❌ 1. Frontend is accessing localhost instead of VPS

**Cause:** NEXT_PUBLIC_* were incorrect during build.

**Solution:**

```bash
docker compose down
docker compose build --no-cache
docker compose up -d
```

---

## ❌ 2. Playwright crashes with a sandbox error

**Cause:** Docker doesn't have the required system libraries.

**Check the Dockerfile contains:**

```
playwright install --with-deps chromium
ENV PLAYWRIGHT_BROWSERS_PATH=/app/playwright-browsers
```

Rebuild the image.

---

## ❌ 3. WebSocket doesn't connect

Check:

- NEXT_PUBLIC_WS_URL uses `ws://` or `wss://`
- CORS_ORIGINS matches frontend origin
- Port 8000 is open:

```bash
sudo ufw allow 8000
sudo ufw allow 3000
```

---

## ❌ 4. "No space left on device" error

Playwright + Chromium require ~1–1.5GB of RAM.

Recommended:
- Minimum 2GB RAM
- WORKER_CONCURRENCY ≤ 2

---

## ❌ 5. 409 Conflict when deleting job

This is correct behavior (PRD M1.5):
Cannot delete `status='running'`.

Wait for completion or restart the container.

---

# ✅ Recommended VPS Configuration

| Parameter | Minimum |
|----------|---------|
| RAM | 2 GB |
| CPU | 2 vCPU |
| Disk | 20 GB |
| OS | Ubuntu 22.04/24.04 |

---