from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from fastapi.responses import JSONResponse

from backend.config import get_artifact_path
from backend.database import get_connection

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.get("/{job_id}/download", response_model=None)
def download_artifact(job_id: int) -> FileResponse | JSONResponse:
    conn = get_connection()
    try:
        job = conn.execute(
            "SELECT id, status, created_at FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if job is None:
            raise HTTPException(status_code=404, detail="Job not found")

        if job["status"] != "done":
            return JSONResponse(
                status_code=409,
                content={
                    "detail": "Job not completed",
                    "current_status": job["status"],
                },
            )

        artifact_path = get_artifact_path(job_id)
        if not artifact_path.exists():
            raise HTTPException(
                status_code=500,
                detail="Artifact file missing from disk",
            )

        created_date = str(job["created_at"])[:10]
        filename = f"uniqueized_{job_id}_{created_date}.zip"
        return FileResponse(
            path=artifact_path,
            media_type="application/zip",
            filename=filename,
        )
    finally:
        conn.close()
