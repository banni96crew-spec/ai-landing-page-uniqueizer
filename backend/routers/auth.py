import asyncio
import hashlib
import hmac
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from backend import config
from backend.database import get_connection
from backend.schemas import (
    AccountResponse,
    LoginRequest,
    LogoutResponse,
    RegisterRequest,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

PLAN_SITE_LIMITS: dict[str, int | None] = {
    "trial": 3,
    "standard": 25,
    "premium": None,
}


def _utc_timestamp_after_days(days: int) -> str:
    future = datetime.now(timezone.utc) + timedelta(days=days)
    return future.replace(tzinfo=None, microsecond=0).isoformat(sep=" ")


def _cleanup_expired_sessions(conn: sqlite3.Connection) -> None:
    conn.execute(
        "DELETE FROM auth_sessions WHERE expires_at <= datetime('now')"
    )


def _hash_password(password: str, salt_hex: str) -> str:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=bytes.fromhex(salt_hex),
        n=2**14,
        r=8,
        p=1,
    ).hex()


def _verify_password(password: str, salt_hex: str, expected_hash: str) -> bool:
    candidate = _hash_password(password, salt_hex)
    return hmac.compare_digest(candidate, expected_hash)


def _hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _build_account_payload(
    conn: sqlite3.Connection,
    user_row: sqlite3.Row,
) -> dict[str, object]:
    count_row = conn.execute(
        "SELECT COUNT(*) AS cnt FROM jobs WHERE status = 'done'"
    ).fetchone()
    sites_used = int(count_row["cnt"]) if count_row is not None else 0
    plan = str(user_row["plan"])
    limit = PLAN_SITE_LIMITS.get(plan)
    sites_remaining = None if limit is None else max(limit - sites_used, 0)
    return {
        "login": str(user_row["login"]),
        "telegram_username": str(user_row["telegram_username"] or ""),
        "plan": plan,
        "sites_used": sites_used,
        "sites_remaining": sites_remaining,
    }


def _create_session(conn: sqlite3.Connection, user_id: int) -> str:
    raw_token = secrets.token_urlsafe(32)
    session_hash = _hash_session_token(raw_token)
    expires_at = _utc_timestamp_after_days(config.AUTH_SESSION_TTL_DAYS)
    conn.execute("DELETE FROM auth_sessions WHERE user_id = ?", (user_id,))
    conn.execute(
        """
        INSERT INTO auth_sessions (user_id, session_token_hash, expires_at)
        VALUES (?, ?, ?)
        """,
        (user_id, session_hash, expires_at),
    )
    return raw_token


def _set_session_cookie(response: Response, raw_token: str) -> None:
    max_age = config.AUTH_SESSION_TTL_DAYS * 24 * 60 * 60
    response.set_cookie(
        key=config.AUTH_SESSION_COOKIE_NAME,
        value=raw_token,
        httponly=True,
        secure=config.AUTH_COOKIE_SECURE,
        samesite="lax",
        max_age=max_age,
    )


def _delete_session_cookie(response: Response) -> None:
    response.delete_cookie(
        key=config.AUTH_SESSION_COOKIE_NAME,
        httponly=True,
        secure=config.AUTH_COOKIE_SECURE,
        samesite="lax",
    )


def _get_session_token_from_request(request: Request) -> str:
    token = request.cookies.get(config.AUTH_SESSION_COOKIE_NAME, "").strip()
    if not token:
        raise HTTPException(status_code=401, detail="Authentication required")
    return token


def _load_authenticated_user_sync(session_token: str) -> dict[str, object]:
    conn = get_connection()
    try:
        _cleanup_expired_sessions(conn)
        session_hash = _hash_session_token(session_token)
        row = conn.execute(
            """
            SELECT
                u.id,
                u.login,
                u.telegram_username,
                u.plan,
                u.created_at,
                u.updated_at
            FROM auth_sessions AS s
            JOIN users AS u ON u.id = s.user_id
            WHERE s.session_token_hash = ?
              AND s.expires_at > datetime('now')
            LIMIT 1
            """,
            (session_hash,),
        ).fetchone()
        if row is None:
            conn.execute(
                "DELETE FROM auth_sessions WHERE session_token_hash = ?",
                (session_hash,),
            )
            conn.commit()
            raise HTTPException(status_code=401, detail="Authentication required")

        payload = dict(row)
        payload["account"] = _build_account_payload(conn, row)
        conn.commit()
        return payload
    finally:
        conn.close()


async def get_authenticated_user(request: Request) -> dict[str, object]:
    session_token = _get_session_token_from_request(request)
    return await asyncio.to_thread(_load_authenticated_user_sync, session_token)


def validate_session_token_sync(session_token: str) -> None:
    """Validate session for non-HTTP contexts (e.g. WebSocket). Raises HTTPException(401) if invalid."""
    cleaned = session_token.strip()
    if not cleaned:
        raise HTTPException(status_code=401, detail="Authentication required")
    _load_authenticated_user_sync(cleaned)


@router.post(
    "/register",
    response_model=AccountResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    response: Response,
) -> AccountResponse:
    def _register_sync() -> tuple[dict[str, object], str]:
        conn = get_connection()
        try:
            _cleanup_expired_sessions(conn)
            existing_user = conn.execute(
                "SELECT id FROM users ORDER BY id ASC LIMIT 1"
            ).fetchone()
            if existing_user is not None:
                raise HTTPException(
                    status_code=409,
                    detail="Local account is already registered",
                )

            salt_hex = secrets.token_hex(16)
            password_hash = _hash_password(payload.password, salt_hex)
            cursor = conn.execute(
                """
                INSERT INTO users (login, password_hash, password_salt, telegram_username, plan)
                VALUES (?, ?, ?, ?, 'trial')
                """,
                (
                    payload.login,
                    password_hash,
                    salt_hex,
                    payload.telegram_username,
                ),
            )
            user_id = int(cursor.lastrowid)
            row = conn.execute(
                """
                SELECT id, login, telegram_username, plan, created_at, updated_at
                FROM users
                WHERE id = ?
                """,
                (user_id,),
            ).fetchone()
            assert row is not None
            session_token = _create_session(conn, user_id)
            conn.commit()
            return _build_account_payload(conn, row), session_token
        finally:
            conn.close()

    account_payload, session_token = await asyncio.to_thread(_register_sync)
    _set_session_cookie(response, session_token)
    return AccountResponse.model_validate(account_payload)


@router.post("/login", response_model=AccountResponse)
async def login(
    payload: LoginRequest,
    response: Response,
) -> AccountResponse:
    def _login_sync() -> tuple[dict[str, object], str]:
        conn = get_connection()
        try:
            _cleanup_expired_sessions(conn)
            row = conn.execute(
                """
                SELECT id, login, password_hash, password_salt, telegram_username, plan,
                       created_at, updated_at
                FROM users
                WHERE login = ?
                LIMIT 1
                """,
                (payload.login,),
            ).fetchone()
            if row is None or not _verify_password(
                payload.password,
                str(row["password_salt"]),
                str(row["password_hash"]),
            ):
                raise HTTPException(status_code=401, detail="Invalid login or password")

            session_token = _create_session(conn, int(row["id"]))
            conn.commit()
            return _build_account_payload(conn, row), session_token
        finally:
            conn.close()

    account_payload, session_token = await asyncio.to_thread(_login_sync)
    _set_session_cookie(response, session_token)
    return AccountResponse.model_validate(account_payload)


@router.post("/logout", response_model=LogoutResponse)
async def logout(request: Request, response: Response) -> LogoutResponse:
    session_token = request.cookies.get(config.AUTH_SESSION_COOKIE_NAME, "").strip()

    if session_token:
        session_hash = _hash_session_token(session_token)

        def _logout_sync() -> None:
            conn = get_connection()
            try:
                conn.execute(
                    "DELETE FROM auth_sessions WHERE session_token_hash = ?",
                    (session_hash,),
                )
                conn.commit()
            finally:
                conn.close()

        await asyncio.to_thread(_logout_sync)

    _delete_session_cookie(response)
    return LogoutResponse(detail="logged_out")


@router.get("/me", response_model=AccountResponse)
async def get_current_account(
    user: dict[str, object] = Depends(get_authenticated_user),
) -> AccountResponse:
    return AccountResponse.model_validate(user["account"])


@router.get("/session", response_model=AccountResponse)
async def get_current_session(
    user: dict[str, object] = Depends(get_authenticated_user),
) -> AccountResponse:
    return AccountResponse.model_validate(user["account"])
