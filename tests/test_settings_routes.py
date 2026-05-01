import os
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend import config, database
from backend.routers.auth import router as auth_router
from backend.routers.settings import router as settings_router


class SettingsRouteTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.db"
        self.previous_database_url = config.DATABASE_URL
        config.DATABASE_URL = str(self.db_path)
        database._SCHEMA_ENSURED_PATHS.discard(os.path.abspath(str(self.db_path)))
        database.init_db()

        app = FastAPI()
        app.include_router(auth_router)
        app.include_router(settings_router)
        self.client = TestClient(app)

        register_response = self.client.post(
            "/api/auth/register",
            json={"login": "owner", "password": "supersecret", "telegram_username": ""},
        )
        self.assertEqual(register_response.status_code, 201)

    def tearDown(self) -> None:
        self.client.close()
        config.DATABASE_URL = self.previous_database_url
        database._SCHEMA_ENSURED_PATHS.discard(os.path.abspath(str(self.db_path)))
        self.temp_dir.cleanup()

    def _set_setting(self, key: str, value: str) -> None:
        conn = database.get_connection()
        try:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) "
                "VALUES (?, ?, CURRENT_TIMESTAMP)",
                (key, value),
            )
            conn.commit()
        finally:
            conn.close()

    def _get_setting(self, key: str) -> str:
        conn = database.get_connection()
        try:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            ).fetchone()
            assert row is not None
            return str(row["value"])
        finally:
            conn.close()

    def test_settings_routes_require_authentication(self) -> None:
        anonymous_client = TestClient(self.client.app)
        try:
            get_response = anonymous_client.get("/api/settings")
            put_response = anonymous_client.put(
                "/api/settings",
                json=[{"key": "proxy_url", "value": "http://127.0.0.1:8080"}],
            )
        finally:
            anonymous_client.close()

        self.assertEqual(get_response.status_code, 401)
        self.assertEqual(put_response.status_code, 401)

    def test_get_settings_masks_api_keys_and_hides_anthropic_fields(self) -> None:
        self._set_setting("openai_api_key", "real-openai-key")
        self._set_setting("anthropic_api_key", "real-anthropic-key")
        self._set_setting("anthropic_model", "claude-3-5-sonnet")

        response = self.client.get("/api/settings")

        self.assertEqual(response.status_code, 200)
        payload = {item["key"]: item["value"] for item in response.json()}
        self.assertEqual(payload["openai_api_key"], "***")
        self.assertNotIn("anthropic_api_key", payload)
        self.assertNotIn("anthropic_model", payload)

    def test_put_settings_rejects_hidden_anthropic_fields(self) -> None:
        original_value = self._get_setting("anthropic_api_key")

        response = self.client.put(
            "/api/settings",
            json=[{"key": "anthropic_api_key", "value": "new-secret"}],
        )

        self.assertEqual(response.status_code, 422)
        self.assertIn("anthropic_api_key", response.json()["detail"])
        self.assertEqual(self._get_setting("anthropic_api_key"), original_value)

    def test_put_settings_updates_visible_settings(self) -> None:
        response = self.client.put(
            "/api/settings",
            json=[
                {"key": "proxy_url", "value": "http://127.0.0.1:8080"},
                {"key": "noise_intensity", "value": "0.005"},
            ],
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"updated": 2})
        self.assertEqual(self._get_setting("proxy_url"), "http://127.0.0.1:8080")
        self.assertEqual(self._get_setting("noise_intensity"), "0.005")


if __name__ == "__main__":
    unittest.main()
