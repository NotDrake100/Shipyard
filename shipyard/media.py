from __future__ import annotations

import base64
import mimetypes
from datetime import UTC, datetime
from pathlib import Path


def utc_now() -> datetime:
    return datetime.now(UTC)


def build_request_id(message_id: int) -> str:
    timestamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"{timestamp}-{message_id}"


def ensure_request_dir(inbox_dir: Path, chat_id: int, request_id: str) -> Path:
    request_dir = inbox_dir / str(chat_id) / request_id
    request_dir.mkdir(parents=True, exist_ok=True)
    return request_dir


def ensure_photo_dir(inbox_dir: Path, chat_id: int, message_id: int) -> Path:
    photo_dir = inbox_dir / str(chat_id) / "photos" / build_request_id(message_id)
    photo_dir.mkdir(parents=True, exist_ok=True)
    return photo_dir


def image_to_data_url(path: Path) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"
