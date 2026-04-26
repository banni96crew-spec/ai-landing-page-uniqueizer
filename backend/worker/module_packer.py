import asyncio
import errno
import hashlib
import logging
import os
import shutil
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Iterable

from backend.config import ARTIFACTS_DIR, get_job_dir
from backend.database import get_connection, log_message

logger = logging.getLogger(__name__)

_ZIP_FIXED_DATETIME: Final[tuple[int, int, int, int, int, int]] = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class ArtifactInfo:
    file_path: str
    file_size: int | None
    hash: str | None


def _log_job_message_sync(job_id: int, level: str, message: str) -> None:
    conn = get_connection()
    try:
        log_message(conn, job_id, level, message)
    finally:
        conn.close()


async def _log_job_message(job_id: int, level: str, message: str) -> None:
    await asyncio.to_thread(_log_job_message_sync, job_id, level, message)


def _is_disk_full_error(exc: OSError) -> bool:
    err_no = getattr(exc, "errno", None)
    if err_no == errno.ENOSPC:
        return True
    return "no space left" in str(exc).lower()


def _select_artifact_sync(job_id: int) -> ArtifactInfo | None:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT file_path, file_size, hash FROM artifacts WHERE job_id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return ArtifactInfo(
            file_path=str(row["file_path"]),
            file_size=int(row["file_size"]) if row["file_size"] is not None else None,
            hash=str(row["hash"]) if row["hash"] is not None else None,
        )
    finally:
        conn.close()


def _ensure_output_dir_sync(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)


def _iter_files_sorted(root: Path) -> list[Path]:
    paths: list[Path] = []
    for p in root.rglob("*"):
        try:
            if not p.is_file():
                continue
            if p.is_symlink():
                continue
        except OSError:
            continue
        paths.append(p)
    return sorted(paths, key=lambda p: p.relative_to(root).as_posix())


def _estimate_source_size_sync(rewritten_dir: Path) -> int:
    total = 0
    for p in _iter_files_sorted(rewritten_dir):
        try:
            total += p.stat().st_size
        except OSError:
            continue
    return total


def _assert_has_free_space_sync(output_dir: Path, estimated_bytes: int) -> None:
    usage = shutil.disk_usage(output_dir)
    if usage.free < estimated_bytes:
        raise OSError(
            errno.ENOSPC,
            f"Insufficient disk space: need ~{estimated_bytes}B, free {usage.free}B",
        )


def _zip_write_file(
    *,
    zf: zipfile.ZipFile,
    src_path: Path,
    arcname: str,
    mode_bits: int,
) -> None:
    info = zipfile.ZipInfo(filename=arcname, date_time=_ZIP_FIXED_DATETIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    # Preserve Unix mode bits deterministically (regular file).
    info.external_attr = (mode_bits & 0xFFFF) << 16
    with src_path.open("rb") as src_fp, zf.open(info, "w") as dst_fp:
        shutil.copyfileobj(src_fp, dst_fp, length=1024 * 1024)


def _build_zip_sync(*, rewritten_dir: Path, output_path: Path) -> None:
    if not rewritten_dir.is_dir():
        raise FileNotFoundError(f"Rewritten directory missing: {rewritten_dir}")

    files = _iter_files_sorted(rewritten_dir)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    try:
        if tmp_path.exists():
            tmp_path.unlink()
    except OSError:
        pass

    try:
        with zipfile.ZipFile(tmp_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for src_path in files:
                rel = src_path.relative_to(rewritten_dir).as_posix()
                try:
                    st = src_path.stat()
                    mode_bits = st.st_mode
                except OSError:
                    mode_bits = 0o100644
                _zip_write_file(zf=zf, src_path=src_path, arcname=rel, mode_bits=mode_bits)
        os.replace(tmp_path, output_path)
    except Exception:
        try:
            tmp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def _sha256_file_sync(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        while True:
            chunk = fp.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _artifact_stats_sync(output_path: Path) -> tuple[int, str]:
    file_size = output_path.stat().st_size
    sha = _sha256_file_sync(output_path)
    return file_size, sha


def pack(job_dir: Path, job_id: int, output_dir: Path) -> tuple[Path, int, str]:
    """
    Builds a deterministic ZIP from job_dir/rewritten into {output_dir}/{job_id}.zip.

    Returns: (zip_path, file_size_bytes, sha256_hex)
    """
    rewritten_dir = job_dir / "rewritten"
    output_path = output_dir / f"{job_id}.zip"

    _ensure_output_dir_sync(output_dir)
    estimated = _estimate_source_size_sync(rewritten_dir)
    _assert_has_free_space_sync(output_dir, estimated)
    _build_zip_sync(rewritten_dir=rewritten_dir, output_path=output_path)
    file_size, sha = _artifact_stats_sync(output_path)
    return output_path, file_size, sha


def _insert_artifact_ignore_sync(
    *, job_id: int, file_path: str, file_size: int, hash_hex: str
) -> bool:
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO artifacts (job_id, file_path, file_size, hash)
            VALUES (?, ?, ?, ?)
            """,
            (job_id, file_path, file_size, hash_hex),
        )
        conn.commit()
        return int(cursor.rowcount) == 1
    finally:
        conn.close()


def _update_artifact_sync(
    *, job_id: int, file_path: str, file_size: int, hash_hex: str
) -> None:
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE artifacts
            SET file_path = ?, file_size = ?, hash = ?
            WHERE job_id = ?
            """,
            (file_path, file_size, hash_hex, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def cleanup_job_workdir(job_dir: Path, job_id: int) -> None:
    try:
        shutil.rmtree(job_dir, ignore_errors=True)
    except OSError as exc:
        logger.warning("cleanup_job_workdir failed (job_id=%s path=%s): %s", job_id, job_dir, exc)
        _log_job_message_sync(job_id, "warn", f"cleanup_job_workdir failed: {exc}")


async def module_packer(job_id: int) -> None:
    """
    Module 5: packs rewritten/ into a ZIP artifact and writes artifacts row.

    EC-17: If artifacts record already exists for job_id -> skip packing.
    """
    existing = await asyncio.to_thread(_select_artifact_sync, job_id)
    if existing is not None:
        await _log_job_message(job_id, "info", f"packer: EC-17 skip (artifact exists)")
        return

    job_dir = get_job_dir(job_id)
    output_dir = ARTIFACTS_DIR
    zip_path = output_dir / f"{job_id}.zip"

    try:
        output_path, file_size, hash_hex = await asyncio.to_thread(
            pack, job_dir, job_id, output_dir
        )
    except OSError as exc:
        if _is_disk_full_error(exc):
            await _log_job_message(job_id, "error", f"Disk space error: {exc}")
            await asyncio.to_thread(cleanup_job_workdir, job_dir, job_id)
        raise

    inserted = await asyncio.to_thread(
        _insert_artifact_ignore_sync,
        job_id=job_id,
        file_path=str(output_path),
        file_size=file_size,
        hash_hex=hash_hex,
    )
    if not inserted:
        # EC-17 race: another worker inserted first.
        await _log_job_message(job_id, "info", "packer: EC-17 skip (db row exists)")
    else:
        await _log_job_message(job_id, "info", f"packer: artifact saved ({file_size} bytes)")

    # If the file was created but INSERT OR IGNORE was skipped due to race,
    # keep the file. Update DB only when row exists but points elsewhere.
    db_row = await asyncio.to_thread(_select_artifact_sync, job_id)
    if db_row is not None and db_row.file_path != str(zip_path):
        await asyncio.to_thread(
            _update_artifact_sync,
            job_id=job_id,
            file_path=str(zip_path),
            file_size=file_size,
            hash_hex=hash_hex,
        )

    await asyncio.to_thread(cleanup_job_workdir, job_dir, job_id)

