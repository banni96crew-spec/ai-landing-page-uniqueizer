import asyncio
import json
import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException, status

from backend import config
from backend.database import get_connection
from backend.routers.auth import _build_account_payload, get_authenticated_user
from backend.schemas import AccountResponse, LicenseVerifyRequest

router = APIRouter(prefix="/api/license", tags=["license"])

_VALID_PLANS = {"trial", "standard", "premium"}


async def _verify_license_plan(activation_key: str) -> str:
    # Production validation must happen against a remote licensing service.
    # Local SQLite stores only the accepted plan state after remote verification.
    if not config.LICENSE_SERVER_URL:
        raise HTTPException(
            status_code=503,
            detail="License server is not configured",
        )

    def _request_sync() -> str:
        body = json.dumps({"activation_key": activation_key}).encode("utf-8")
        request = urllib.request.Request(
            url=config.LICENSE_SERVER_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=config.LICENSE_REQUEST_TIMEOUT_SECONDS,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in {400, 401, 403, 404, 409, 422}:
                raise HTTPException(status_code=400, detail="Activation key is invalid") from exc
            raise HTTPException(
                status_code=502,
                detail="License server request failed",
            ) from exc
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            raise HTTPException(
                status_code=502,
                detail="License server request failed",
            ) from exc

        if not bool(payload.get("valid")):
            raise HTTPException(status_code=400, detail="Activation key is invalid")

        plan = str(payload.get("plan", "")).strip().lower()
        if plan not in _VALID_PLANS:
            raise HTTPException(
                status_code=502,
                detail="License server returned an unsupported plan",
            )
        return plan

    return await asyncio.to_thread(_request_sync)


@router.post("/verify", response_model=AccountResponse, status_code=status.HTTP_200_OK)
async def verify_license(
    payload: LicenseVerifyRequest,
    user: dict[str, object] = Depends(get_authenticated_user),
) -> AccountResponse:
    plan = await _verify_license_plan(payload.activation_key)

    def _update_plan_sync() -> dict[str, object]:
        conn = get_connection()
        try:
            conn.execute(
                "UPDATE users SET plan = ? WHERE id = ?",
                (plan, int(user["id"])),
            )
            row = conn.execute(
                """
                SELECT id, login, telegram_username, plan, created_at, updated_at
                FROM users
                WHERE id = ?
                """,
                (int(user["id"]),),
            ).fetchone()
            if row is None:
                raise HTTPException(status_code=404, detail="User not found")

            conn.commit()
            return _build_account_payload(conn, row)
        finally:
            conn.close()

    account_payload = await asyncio.to_thread(_update_plan_sync)
    return AccountResponse.model_validate(account_payload)
