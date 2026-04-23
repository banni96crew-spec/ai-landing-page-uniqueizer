import socket
import shutil
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import Response
from fastapi.responses import JSONResponse

from backend.config import BLOCKED_IP_PREFIXES, MAX_QUEUE_SIZE, get_artifact_path, get_job_dir
from backend.database import get_connection
from backend.job_progress import calculate_progress_pct
from backend.schemas import ArtifactResponse, JobCreateRequest, JobDetailResponse, JobResponse

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


def _get_job_or_404(conn, job_id: int):
    row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return row


def _validate_target_url(target_url: str) -> None:
    if not target_url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400,
            detail="URL must start with http:// or https://",
        )

    parsed = urlparse(target_url)
    if not parsed.hostname:
        raise HTTPException(status_code=422, detail="Cannot resolve hostname")

    try:
        ip = socket.gethostbyname(parsed.hostname)
    except socket.gaierror as exc:
        raise HTTPException(status_code=422, detail="Cannot resolve hostname") from exc

    if any(ip.startswith(prefix) for prefix in BLOCKED_IP_PREFIXES):
        raise HTTPException(
            status_code=422,
            detail="Private/reserved IP addresses are not allowed",
        )


@router.post("", response_model=JobResponse, status_code=status.HTTP_201_CREATED)
def create_job(payload: JobCreateRequest) -> JobResponse | JSONResponse:
    _validate_target_url(payload.target_url)

    conn = get_connection()
    try:
        pending_count_row = conn.execute(
            "SELECT COUNT(*) AS cnt FROM jobs WHERE status = 'pending'"
        ).fetchone()
        pending_count = int(pending_count_row["cnt"])
        if pending_count >= MAX_QUEUE_SIZE:
            return JSONResponse(
                status_code=429,
                content={"error": "queue_full"},
            )

        cursor = conn.execute(
            "INSERT INTO jobs (target_url, status) VALUES (?, 'pending')",
            (payload.target_url,),
        )
        conn.commit()

        row = conn.execute(
            "SELECT id, status, created_at, target_url FROM jobs WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        return JobResponse.model_validate(dict(row))
    finally:
        conn.close()


@router.get("", response_model=list[JobResponse])
def list_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> list[JobResponse]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, status, created_at, target_url "
            "FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [JobResponse.model_validate(dict(row)) for row in rows]
    finally:
        conn.close()


@router.get("/{job_id}", response_model=JobDetailResponse)
def get_job(job_id: int) -> JobDetailResponse:
    conn = get_connection()
    try:
        job = _get_job_or_404(conn, job_id)
        artifact = conn.execute(
            "SELECT id, job_id, file_path, file_size, hash, created_at "
            "FROM artifacts WHERE job_id = ?",
            (job_id,),
        ).fetchone()

        progress_pct = calculate_progress_pct(conn, job_id, str(job["status"]))

        response_payload = {
            "id": job["id"],
            "status": job["status"],
            "target_url": job["target_url"],
            "created_at": job["created_at"],
            "updated_at": job["updated_at"],
            "artifact": ArtifactResponse.model_validate(dict(artifact)) if artifact else None,
            "progress_pct": progress_pct,
        }
        return JobDetailResponse.model_validate(response_payload)
    finally:
        conn.close()


@router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_job(job_id: int) -> Response:
    conn = get_connection()
    try:
        job = _get_job_or_404(conn, job_id)

        if job["status"] == "running":
            raise HTTPException(
                status_code=409,
                detail="Cannot delete a running job",
            )

        get_artifact_path(job_id).unlink(missing_ok=True)

        shutil.rmtree(get_job_dir(job_id), ignore_errors=True)

        conn.execute("DELETE FROM logs WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM artifacts WHERE job_id = ?", (job_id,))
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()

        return Response(status_code=status.HTTP_204_NO_CONTENT)
    finally:
        conn.close()
