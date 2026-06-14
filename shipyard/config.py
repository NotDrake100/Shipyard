from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv
except ModuleNotFoundError:
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    openai_api_key: str
    storage_dir: Path
    transcription_model: str
    vision_model: str
    planning_model: str
    pending_photo_ttl_minutes: int
    telegram_network_timeout_seconds: float
    worktree_root: Path
    enable_server: bool
    server_host: str
    server_port: int

    @property
    def inbox_dir(self) -> Path:
        return self.storage_dir / "inbox"

    @property
    def state_dir(self) -> Path:
        return self.storage_dir / "state"


def load_settings(dotenv_path: str | Path | None = ".env") -> Settings:
    if dotenv_path is not None:
        load_dotenv(dotenv_path=dotenv_path)

    telegram_bot_token = _required_env("TELEGRAM_BOT_TOKEN")
    openai_api_key = _required_env("OPENAI_API_KEY")

    storage_dir = Path(os.getenv("SHIPYARD_STORAGE_DIR", "data")).expanduser()
    transcription_model = os.getenv("OPENAI_TRANSCRIPTION_MODEL", "whisper-1")
    vision_model = os.getenv("OPENAI_VISION_MODEL", "gpt-4o-mini")
    planning_model = os.getenv("OPENAI_PLANNING_MODEL", "gpt-4o-mini")
    pending_photo_ttl_minutes = _int_env("PENDING_PHOTO_TTL_MINUTES", 30)
    telegram_network_timeout_seconds = _float_env("TELEGRAM_NETWORK_TIMEOUT_SECONDS", 30.0)
    worktree_root = Path(os.getenv("SHIPYARD_WORKTREE_ROOT", "/tmp/shipyard")).expanduser()
    enable_server = _bool_env("SHIPYARD_ENABLE_SERVER", True)
    server_host = os.getenv("SHIPYARD_SERVER_HOST", "127.0.0.1")
    server_port = _int_env("SHIPYARD_SERVER_PORT", 5050)

    return Settings(
        telegram_bot_token=telegram_bot_token,
        openai_api_key=openai_api_key,
        storage_dir=storage_dir,
        transcription_model=transcription_model,
        vision_model=vision_model,
        planning_model=planning_model,
        pending_photo_ttl_minutes=pending_photo_ttl_minutes,
        telegram_network_timeout_seconds=telegram_network_timeout_seconds,
        worktree_root=worktree_root,
        enable_server=enable_server,
        server_host=server_host,
        server_port=server_port,
    )


def _required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def _int_env(name: str, default: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default

    try:
        value = int(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc

    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")

    return value


def _float_env(name: str, default: float) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default

    try:
        value = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number") from exc

    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")

    return value


def _bool_env(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, "").strip().lower()
    if not raw_value:
        return default
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be true or false")
