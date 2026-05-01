from fastapi import APIRouter, Depends, HTTPException

from backend.database import get_connection
from backend.routers.auth import get_authenticated_user
from backend.schemas import SettingResponse, SettingUpsertRequest

router = APIRouter(prefix="/api/settings", tags=["settings"])
HIDDEN_SETTINGS_KEYS = {"anthropic_api_key", "anthropic_model"}


@router.get("", response_model=list[SettingResponse])
def get_settings(
    _user: dict[str, object] = Depends(get_authenticated_user),
) -> list[SettingResponse]:
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT key, value FROM settings WHERE key NOT IN (?, ?) ORDER BY key ASC",
            tuple(sorted(HIDDEN_SETTINGS_KEYS)),
        ).fetchall()
        masked = []
        for row in rows:
            key = row["key"]
            value = "***" if key.endswith("_api_key") else row["value"]
            masked.append(SettingResponse(key=key, value=value))
        return masked
    finally:
        conn.close()


@router.put("")
def upsert_settings(
    payload: list[SettingUpsertRequest],
    _user: dict[str, object] = Depends(get_authenticated_user),
) -> dict[str, int]:
    for item in payload:
        if item.key in HIDDEN_SETTINGS_KEYS:
            raise HTTPException(
                status_code=422,
                detail=f"{item.key} is not exposed by the settings API",
            )

        if item.key == "noise_intensity":
            try:
                noise = float(item.value)
            except ValueError as exc:
                raise HTTPException(
                    status_code=422,
                    detail="noise_intensity must be a float between 0.0 and 0.01",
                ) from exc
            if not 0.0 <= noise <= 0.01:
                raise HTTPException(
                    status_code=422,
                    detail="noise_intensity must be between 0.0 and 0.01",
                )

        if item.key == "ai_provider" and item.value not in {"openai", "anthropic"}:
            raise HTTPException(
                status_code=422,
                detail="ai_provider must be 'openai' or 'anthropic'",
            )

    conn = get_connection()
    try:
        for item in payload:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                (item.key, item.value),
            )
        conn.commit()
        return {"updated": len(payload)}
    finally:
        conn.close()
