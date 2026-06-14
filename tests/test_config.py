from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from shipyard.config import load_settings


class LoadSettingsTest(unittest.TestCase):
    def test_load_settings_reads_required_environment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            env = {
                "TELEGRAM_BOT_TOKEN": "telegram-token",
                "OPENAI_API_KEY": "openai-key",
                "SHIPYARD_STORAGE_DIR": tmp_dir,
                "OPENAI_PLANNING_MODEL": "gpt-test-planner",
                "PENDING_PHOTO_TTL_MINUTES": "15",
                "TELEGRAM_NETWORK_TIMEOUT_SECONDS": "45",
            }

            with patch.dict(os.environ, env, clear=True):
                settings = load_settings(dotenv_path=None)

        self.assertEqual(settings.telegram_bot_token, "telegram-token")
        self.assertEqual(settings.openai_api_key, "openai-key")
        self.assertEqual(settings.storage_dir, Path(tmp_dir))
        self.assertEqual(settings.planning_model, "gpt-test-planner")
        self.assertEqual(settings.pending_photo_ttl_minutes, 15)
        self.assertEqual(settings.telegram_network_timeout_seconds, 45.0)

    def test_load_settings_requires_telegram_token(self) -> None:
        env = {"OPENAI_API_KEY": "openai-key"}

        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "TELEGRAM_BOT_TOKEN"):
                load_settings(dotenv_path=None)

    def test_load_settings_rejects_invalid_photo_ttl(self) -> None:
        env = {
            "TELEGRAM_BOT_TOKEN": "telegram-token",
            "OPENAI_API_KEY": "openai-key",
            "PENDING_PHOTO_TTL_MINUTES": "0",
        }

        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "greater than zero"):
                load_settings(dotenv_path=None)


if __name__ == "__main__":
    unittest.main()
