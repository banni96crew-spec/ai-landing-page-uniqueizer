import os
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE_PATH = PROJECT_ROOT / ".env"

# Load the repository root .env once before reading any settings values.
load_dotenv(ENV_FILE_PATH)


def _get_optional_env(name: str) -> str | None:
    value = os.environ.get(name)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


DEFAULT_DATABASE_URL = str(Path(__file__).resolve().parent / "data" / "app.db")
JOBS_WORKDIR = Path(os.environ.get("JOBS_WORKDIR", "/app/volumes/jobs"))
ARTIFACTS_DIR = Path(os.environ.get("ARTIFACTS_DIR", "/app/volumes/artifacts"))
DATABASE_URL = os.environ.get("DATABASE_URL", DEFAULT_DATABASE_URL)

JOB_TIMEOUT_SECONDS = int(os.environ.get("JOB_TIMEOUT_SECONDS", "600"))
WORKER_CONCURRENCY = int(os.environ.get("WORKER_CONCURRENCY", "2"))
WORKER_POLL_INTERVAL = int(os.environ.get("WORKER_POLL_INTERVAL", "2"))
MAX_PAGE_SIZE_MB = int(os.environ.get("MAX_PAGE_SIZE_MB", "50"))
ASSET_MAX_SIZE_BYTES = int(
    os.environ.get("ASSET_MAX_SIZE_BYTES", str(50 * 1024 * 1024))
)
MAX_QUEUE_SIZE = int(os.environ.get("MAX_QUEUE_SIZE", "100"))
SCRAPER_PAGE_TIMEOUT_SECONDS = int(
    os.environ.get("SCRAPER_PAGE_TIMEOUT_SECONDS", "60")
)
ASSET_DOWNLOAD_TIMEOUT_SECONDS = int(
    os.environ.get("ASSET_DOWNLOAD_TIMEOUT_SECONDS", "15")
)
AI_REQUEST_TIMEOUT_SECONDS = int(os.environ.get("AI_REQUEST_TIMEOUT_SECONDS", "30"))
AI_BATCH_SIZE = int(os.environ.get("AI_BATCH_SIZE", "20"))
REWRITE_FAIL_THRESHOLD = float(os.environ.get("REWRITE_FAIL_THRESHOLD", "0.5"))
LICENSE_REQUEST_TIMEOUT_SECONDS = int(
    os.environ.get("LICENSE_REQUEST_TIMEOUT_SECONDS", "10")
)

ARTIFACT_TTL_DAYS = int(os.environ.get("ARTIFACT_TTL_DAYS", "7"))
FAILED_JOB_TTL_DAYS = int(os.environ.get("FAILED_JOB_TTL_DAYS", "7"))
AUTH_SESSION_TTL_DAYS = int(os.environ.get("AUTH_SESSION_TTL_DAYS", "30"))
AUTH_SESSION_COOKIE_NAME = os.environ.get("AUTH_SESSION_COOKIE_NAME", "ai_lpu_session")
AUTH_COOKIE_SECURE = os.environ.get("AUTH_COOKIE_SECURE", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
LICENSE_SERVER_URL: str | None = _get_optional_env("LICENSE_SERVER_URL")

CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.environ.get(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if origin.strip()
]

BLOCKED_IP_PREFIXES = (
    "10.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "192.168.",
    "127.",
    "0.",
    "169.254.",
    "::1",
    "fc00:",
    "fe80:",
)


def get_job_dir(job_id: int) -> Path:
    return JOBS_WORKDIR / str(job_id)


def get_artifact_path(job_id: int) -> Path:
    return ARTIFACTS_DIR / f"{job_id}.zip"
