import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config, database
from backend.routers.auth import router as auth_router
from backend.routers.jobs import router as jobs_router
from backend.routers.license import router as license_router


class AuthLicenseRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.previous_database_url = config.DATABASE_URL
        self.previous_license_server_url = config.LICENSE_SERVER_URL
        config.DATABASE_URL = str(self.db_path)
        config.LICENSE_SERVER_URL = None
        database._SCHEMA_ENSURED_PATHS.discard(os.path.abspath(str(self.db_path)))
        database.init_db()

        app = FastAPI()
        app.include_router(auth_router)
        app.include_router(license_router)
        app.include_router(jobs_router)
        self.client = TestClient(app)

    def tearDown(self) -> None:
        self.client.close()
        config.DATABASE_URL = self.previous_database_url
        config.LICENSE_SERVER_URL = self.previous_license_server_url
        database._SCHEMA_ENSURED_PATHS.discard(os.path.abspath(str(self.db_path)))
        self.temp_dir.cleanup()

    def _create_job(self, status: str) -> int:
        conn = database.get_connection()
        try:
            cursor = conn.execute(
                "INSERT INTO jobs (target_url, status) VALUES (?, ?)",
                ("https://example.com", status),
            )
            conn.commit()
            return int(cursor.lastrowid)
        finally:
            conn.close()

    def _count_sessions(self) -> int:
        conn = database.get_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM auth_sessions"
            ).fetchone()
            return int(row["cnt"])
        finally:
            conn.close()

    def _get_user_plan(self) -> str:
        conn = database.get_connection()
        try:
            row = conn.execute("SELECT plan FROM users LIMIT 1").fetchone()
            assert row is not None
            return str(row["plan"])
        finally:
            conn.close()

    def test_register_sets_cookie_and_uses_done_jobs_for_trial_quota(self) -> None:
        self._create_job("done")
        self._create_job("failed")
        self._create_job("done")

        response = self.client.post(
            "/api/auth/register",
            json={
                "login": "Admin",
                "password": "supersecret",
                "telegram_username": "@uniqueizer",
            },
        )

        self.assertEqual(response.status_code, 201)
        self.assertIn("ai_lpu_session=", response.headers.get("set-cookie", ""))
        self.assertIn("HttpOnly", response.headers.get("set-cookie", ""))
        self.assertEqual(
            response.json(),
            {
                "login": "admin",
                "telegram_username": "uniqueizer",
                "plan": "trial",
                "sites_used": 2,
                "sites_remaining": 1,
            },
        )

    def test_register_rejects_second_local_account(self) -> None:
        first_response = self.client.post(
            "/api/auth/register",
            json={"login": "owner", "password": "supersecret", "telegram_username": ""},
        )
        self.assertEqual(first_response.status_code, 201)

        second_response = self.client.post(
            "/api/auth/register",
            json={"login": "another", "password": "supersecret", "telegram_username": ""},
        )

        self.assertEqual(second_response.status_code, 409)
        self.assertEqual(
            second_response.json(),
            {"detail": "Local account is already registered"},
        )

    def test_login_session_and_logout_round_trip(self) -> None:
        register_response = self.client.post(
            "/api/auth/register",
            json={"login": "owner", "password": "supersecret", "telegram_username": ""},
        )
        self.assertEqual(register_response.status_code, 201)
        self.assertEqual(self._count_sessions(), 1)

        logout_response = self.client.post("/api/auth/logout")
        self.assertEqual(logout_response.status_code, 200)
        self.assertEqual(logout_response.json(), {"detail": "logged_out"})
        self.assertEqual(self._count_sessions(), 0)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

        invalid_login = self.client.post(
            "/api/auth/login",
            json={"login": "owner", "password": "wrong-pass"},
        )
        self.assertEqual(invalid_login.status_code, 401)

        login_response = self.client.post(
            "/api/auth/login",
            json={"login": "owner", "password": "supersecret"},
        )
        self.assertEqual(login_response.status_code, 200)
        self.assertIn("ai_lpu_session=", login_response.headers.get("set-cookie", ""))
        self.assertEqual(self.client.get("/api/auth/session").status_code, 200)

    def test_license_verify_requires_authenticated_session(self) -> None:
        response = self.client.post(
            "/api/license/verify",
            json={"activation_key": "PREMIUM-KEY"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Authentication required"})

    def test_jobs_create_requires_authenticated_session(self) -> None:
        response = self.client.post(
            "/api/jobs",
            json={"target_url": "https://example.com"},
        )

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json(), {"detail": "Authentication required"})

    def test_license_verify_updates_plan_for_authenticated_user(self) -> None:
        self._create_job("done")
        self.client.post(
            "/api/auth/register",
            json={"login": "owner", "password": "supersecret", "telegram_username": ""},
        )

        with patch(
            "backend.routers.license._verify_license_plan",
            new=AsyncMock(return_value="premium"),
        ):
            response = self.client.post(
                "/api/license/verify",
                json={"activation_key": "PREMIUM-KEY"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["plan"], "premium")
        self.assertEqual(response.json()["sites_used"], 1)
        self.assertIsNone(response.json()["sites_remaining"])
        self.assertEqual(self._get_user_plan(), "premium")

    def test_license_verify_uses_done_jobs_only_for_standard_quota(self) -> None:
        self._create_job("done")
        self._create_job("failed")
        self._create_job("done")
        self.client.post(
            "/api/auth/register",
            json={"login": "owner", "password": "supersecret", "telegram_username": ""},
        )

        with patch(
            "backend.routers.license._verify_license_plan",
            new=AsyncMock(return_value="standard"),
        ):
            response = self.client.post(
                "/api/license/verify",
                json={"activation_key": "STANDARD-KEY"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "login": "owner",
                "telegram_username": "",
                "plan": "standard",
                "sites_used": 2,
                "sites_remaining": 23,
            },
        )
        self.assertEqual(self._get_user_plan(), "standard")

    def test_license_verify_returns_503_when_server_is_not_configured(self) -> None:
        self.client.post(
            "/api/auth/register",
            json={"login": "owner", "password": "supersecret", "telegram_username": ""},
        )

        response = self.client.post(
            "/api/license/verify",
            json={"activation_key": "STANDARD-KEY"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.json(),
            {"detail": "License server is not configured"},
        )

    def test_init_db_adds_auth_tables_to_legacy_database(self) -> None:
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        raw = sqlite3.connect(legacy_path)
        try:
            raw.executescript(
                """
                PRAGMA foreign_keys=OFF;
                CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_url TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    error_message TEXT,
                    created_at TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT ''
                );
                CREATE TABLE artifacts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    file_path TEXT NOT NULL,
                    file_size INTEGER,
                    hash TEXT
                );
                CREATE TABLE settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at TEXT DEFAULT ''
                );
                CREATE TABLE logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id INTEGER NOT NULL,
                    level TEXT NOT NULL DEFAULT 'info',
                    message TEXT NOT NULL,
                    timestamp TEXT DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            raw.commit()
        finally:
            raw.close()

        config.DATABASE_URL = str(legacy_path)
        database._SCHEMA_ENSURED_PATHS.discard(os.path.abspath(str(legacy_path)))
        database.init_db()

        conn = database.get_connection()
        try:
            tables = {
                str(row["name"])
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
        finally:
            conn.close()

        self.assertIn("users", tables)
        self.assertIn("auth_sessions", tables)
        self.assertIn("jobs", tables)


if __name__ == "__main__":
    unittest.main()
