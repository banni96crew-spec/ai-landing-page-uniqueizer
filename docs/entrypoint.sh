#!/usr/bin/env bash
# ==========================================================
# entrypoint.sh
# AI Landing Page Uniqueizer
# Запуск FastAPI (uvicorn) + Next.js в одном контейнере
# Fail-fast + корректная обработка сигналов
# ==========================================================

set -Eeuo pipefail

# ----------------------------------------------------------
# 1. Проверка обязательных переменных окружения
# ----------------------------------------------------------
: "${BACKEND_DIR:?Environment variable BACKEND_DIR is required}"
: "${FRONTEND_DIR:?Environment variable FRONTEND_DIR is required}"
: "${BACKEND_PORT:?Environment variable BACKEND_PORT is required}"
: "${FRONTEND_PORT:?Environment variable FRONTEND_PORT is required}"

echo "[entrypoint] Starting AI Landing Page Uniqueizer..."
echo "[entrypoint] Backend dir:   ${BACKEND_DIR}"
echo "[entrypoint] Frontend dir:  ${FRONTEND_DIR}"
echo "[entrypoint] Backend port:  ${BACKEND_PORT}"
echo "[entrypoint] Frontend port: ${FRONTEND_PORT}"

BACKEND_PID=""
FRONTEND_PID=""

# ----------------------------------------------------------
# 2. Корректное завершение по сигналам
# ----------------------------------------------------------
graceful_shutdown() {
    echo "[entrypoint] Caught termination signal. Shutting down..."

    # Отправляем SIGTERM дочерним процессам
    if [[ -n "${BACKEND_PID}" ]] && kill -0 "${BACKEND_PID}" 2>/dev/null; then
        kill -TERM "${BACKEND_PID}" 2>/dev/null || true
    fi

    if [[ -n "${FRONTEND_PID}" ]] && kill -0 "${FRONTEND_PID}" 2>/dev/null; then
        kill -TERM "${FRONTEND_PID}" 2>/dev/null || true
    fi

    # Ждём их завершения
    wait || true

    echo "[entrypoint] Shutdown complete."
    exit 0
}

trap graceful_shutdown SIGINT SIGTERM

# ----------------------------------------------------------
# 3. Запуск Backend (FastAPI / Uvicorn)
# ----------------------------------------------------------
cd "${BACKEND_DIR}"

echo "[entrypoint] Starting backend..."
uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port "${BACKEND_PORT}" \
    --proxy-headers \
    --forwarded-allow-ips='*' &
BACKEND_PID=$!

echo "[entrypoint] Backend started (PID: ${BACKEND_PID})"

# ----------------------------------------------------------
# 4. Запуск Frontend (Next.js)
# ----------------------------------------------------------
cd "${FRONTEND_DIR}"

echo "[entrypoint] Starting frontend..."
npm run start -- \
    --port "${FRONTEND_PORT}" \
    --hostname 0.0.0.0 &
FRONTEND_PID=$!

echo "[entrypoint] Frontend started (PID: ${FRONTEND_PID})"

# ----------------------------------------------------------
# 5. Fail-fast мониторинг
# wait -n завершится, когда завершится ЛЮБОЙ процесс
# ----------------------------------------------------------
set +e
wait -n "${BACKEND_PID}" "${FRONTEND_PID}"
EXIT_CODE=$?
set -e

echo "[entrypoint] One process exited (code=${EXIT_CODE}). Initiating shutdown..."

# Останавливаем второй процесс
graceful_shutdown

# Если graceful_shutdown не завершил (fallback)
exit "${EXIT_CODE}"