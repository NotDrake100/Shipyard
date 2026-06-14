from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path


@dataclass(frozen=True)
class PendingPhoto:
    chat_id: int
    message_id: int
    file_path: Path
    created_at: datetime

    def to_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["file_path"] = str(self.file_path)
        payload["created_at"] = self.created_at.isoformat()
        return payload

    @classmethod
    def from_json(cls, payload: dict[str, object]) -> "PendingPhoto":
        return cls(
            chat_id=int(payload["chat_id"]),
            message_id=int(payload["message_id"]),
            file_path=Path(str(payload["file_path"])),
            created_at=datetime.fromisoformat(str(payload["created_at"])),
        )


class PendingPhotoStore:
    def __init__(self, state_dir: Path) -> None:
        self._state_dir = state_dir
        self._path = state_dir / "pending_photos.json"

    def remember(self, photo: PendingPhoto) -> None:
        state = self._load()
        state[str(photo.chat_id)] = photo.to_json()
        self._save(state)

    def get_recent(self, chat_id: int, ttl_minutes: int) -> PendingPhoto | None:
        state = self._load()
        payload = state.get(str(chat_id))
        if not payload:
            return None

        photo = PendingPhoto.from_json(payload)
        expires_at = photo.created_at + timedelta(minutes=ttl_minutes)
        if datetime.now(UTC) > expires_at or not photo.file_path.exists():
            self.clear(chat_id)
            return None

        return photo

    def clear(self, chat_id: int) -> None:
        state = self._load()
        state.pop(str(chat_id), None)
        self._save(state)

    def _load(self) -> dict[str, dict[str, object]]:
        if not self._path.exists():
            return {}

        with self._path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)

        if not isinstance(payload, dict):
            return {}

        return payload

    def _save(self, state: dict[str, dict[str, object]]) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True)
        tmp_path = self._path.with_suffix(".json.tmp")
        with tmp_path.open("w", encoding="utf-8") as handle:
            json.dump(state, handle, indent=2, sort_keys=True)
        tmp_path.replace(self._path)
