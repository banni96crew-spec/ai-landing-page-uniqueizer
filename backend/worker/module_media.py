import asyncio
import errno
import logging
from pathlib import Path
from typing import Final

from backend.config import get_job_dir
from backend.database import get_connection, log_message

logger = logging.getLogger(__name__)

SUPPORTED_FORMATS: Final[set[str]] = {".jpg", ".jpeg", ".png", ".webp"}
SKIP_WARN_FORMATS: Final[set[str]] = {".svg", ".gif"}


def _log_job_message_sync(job_id: int, level: str, message: str) -> None:
    conn = get_connection()
    try:
        log_message(conn, job_id, level, message)
    finally:
        conn.close()


def _load_noise_intensity_sync() -> float:
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?",
            ("noise_intensity",),
        ).fetchone()
        raw = str(row["value"]) if row is not None else "0.01"
    finally:
        conn.close()

    try:
        value = float(raw)
    except ValueError:
        value = 0.01

    # Hard clamp: must never exceed 1% by project rules.
    if value < 0.0:
        return 0.0
    if value > 0.01:
        return 0.01
    return value


def _list_image_paths_sync(images_dir: Path) -> list[Path]:
    if not images_dir.is_dir():
        return []
    return [p for p in images_dir.rglob("*") if p.is_file()]


def _is_disk_full_error(exc: OSError) -> bool:
    err_no = getattr(exc, "errno", None)
    if err_no == errno.ENOSPC:
        return True
    return "no space left" in str(exc).lower()


def _process_image_inplace_sync(img_path: Path, noise_intensity: float, job_id: int) -> None:
    from PIL import Image, UnidentifiedImageError  # local import: heavy dependency
    import numpy as np  # local import: heavy dependency

    suffix = img_path.suffix.lower()
    filename = img_path.name

    if suffix in SKIP_WARN_FORMATS:
        _log_job_message_sync(job_id, "warn", f"Skipped {filename}: format not supported")
        return

    if suffix not in SUPPORTED_FORMATS:
        return

    try:
        with Image.open(img_path) as opened:
            img = opened.convert("RGB")
    except UnidentifiedImageError:
        _log_job_message_sync(job_id, "warn", f"Corrupt image, skipping: {filename}")
        return
    except OSError as exc:
        if _is_disk_full_error(exc):
            raise
        _log_job_message_sync(job_id, "warn", f"Image open failed, skipping: {filename}")
        return

    # Full metadata cleanup: roundtrip through numpy.
    img = Image.fromarray(np.array(img))

    w, h = img.size
    if w < 2 or h < 2:
        _log_job_message_sync(job_id, "warn", f"Image too small to crop, skipping: {filename}")
        return

    img = img.crop((0, 0, w - 1, h - 1))

    arr = np.array(img).astype(np.float32)
    noise = np.random.normal(0.0, noise_intensity * 255.0, arr.shape).astype(np.float32)
    noisy = np.clip(arr + noise, 0.0, 255.0).astype(np.uint8)
    out = Image.fromarray(noisy, mode="RGB")

    save_kwargs: dict[str, object] = {}
    if suffix in (".jpg", ".jpeg"):
        save_kwargs = {"format": "JPEG", "quality": 92}
    elif suffix == ".png":
        save_kwargs = {"format": "PNG", "optimize": True}
    elif suffix == ".webp":
        save_kwargs = {"format": "WEBP", "quality": 92}

    try:
        out.save(img_path, **save_kwargs)
    except OSError as exc:
        if _is_disk_full_error(exc):
            raise
        _log_job_message_sync(job_id, "warn", f"Image save failed, skipping: {filename}")


async def module_media_uniqueizer(job_id: int) -> None:
    """
    M5: In-place media uniqueization for rewritten/assets/images.

    - Supported: jpg/jpeg/png/webp
    - Skip + warn: svg/gif
    - EC-08: corrupt image -> warn and continue
    - EC-09: disk full -> raise (pipeline fails job)
    """
    job_dir = get_job_dir(job_id)
    images_dir = job_dir / "rewritten" / "assets" / "images"

    noise_intensity = await asyncio.to_thread(_load_noise_intensity_sync)
    paths = await asyncio.to_thread(_list_image_paths_sync, images_dir)
    logger.info("module_media: %d files under %s (job_id=%s)", len(paths), images_dir, job_id)

    for path in paths:
        await asyncio.to_thread(_process_image_inplace_sync, path, noise_intensity, job_id)

