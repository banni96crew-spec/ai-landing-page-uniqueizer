import asyncio
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from backend.config import ARTIFACTS_DIR
from backend.database import get_connection
from backend.routers.auth import get_authenticated_user

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.get("/{job_id}/download", response_model=None)
async def download_artifact(
    job_id: int,
    _user: dict[str, object] = Depends(get_authenticated_user),
) -> FileResponse | JSONResponse:
    def _resolve_artifact_path_sync(file_path_raw: str) -> Path:
        candidate = Path(file_path_raw)
        artifacts_root = ARTIFACTS_DIR.resolve()
        resolved = candidate.resolve()

        if resolved.suffix.lower() != ".zip":
            raise HTTPException(status_code=500, detail="Artifact file missing from disk")

        try:
            resolved.relative_to(artifacts_root)
        except ValueError as exc:
            raise HTTPException(status_code=500, detail="Artifact file missing from disk") from exc

        if not resolved.exists() or not resolved.is_file():
            raise HTTPException(status_code=500, detail="Artifact file missing from disk")

        return resolved

    def _load_sync() -> dict[str, str | Path]:
        conn = get_connection()
        try:
            job = conn.execute(
                "SELECT id, status, created_at FROM jobs WHERE id = ?",
                (job_id,),
            ).fetchone()
            if job is None:
                raise HTTPException(status_code=404, detail="Job not found")

            status = str(job["status"])
            if status != "done":
                return {"status": status}

            artifact = conn.execute(
                "SELECT file_path FROM artifacts WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            if artifact is None:
                raise HTTPException(status_code=500, detail="Artifact file missing from disk")

            file_path_raw = str(artifact["file_path"] or "").strip()
            if not file_path_raw:
                raise HTTPException(status_code=500, detail="Artifact file missing from disk")

            artifact_path = _resolve_artifact_path_sync(file_path_raw)
            created_date = str(job["created_at"])[:10]
            return {"status": status, "artifact_path": artifact_path, "created_date": created_date}
        finally:
            conn.close()

    payload = await asyncio.to_thread(_load_sync)
    status = str(payload.get("status", ""))
    if status != "done":
        return JSONResponse(
            status_code=409,
            content={"detail": "Job not completed", "current_status": status},
        )

    artifact_path = payload["artifact_path"]
    created_date = str(payload["created_date"])
    filename = f"uniqueized_{job_id}_{created_date}.zip"
    return FileResponse(
        path=artifact_path,
        media_type="application/zip",
        filename=filename,
    )
