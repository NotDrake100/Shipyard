from __future__ import annotations

from datetime import UTC, datetime, timedelta
import tempfile
import unittest
from pathlib import Path

from shipyard.state import PendingPhoto, PendingPhotoStore


class PendingPhotoStoreTest(unittest.TestCase):
    def test_pending_photo_store_returns_recent_photo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            photo_path = root / "sketch.jpg"
            photo_path.write_bytes(b"image")
            store = PendingPhotoStore(root / "state")

            store.remember(
                PendingPhoto(
                    chat_id=123,
                    message_id=456,
                    file_path=photo_path,
                    created_at=datetime.now(UTC),
                )
            )

            pending = store.get_recent(chat_id=123, ttl_minutes=30)

        self.assertIsNotNone(pending)
        self.assertEqual(pending.file_path, photo_path)
        self.assertEqual(pending.message_id, 456)

    def test_pending_photo_store_expires_old_photo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            photo_path = root / "sketch.jpg"
            photo_path.write_bytes(b"image")
            store = PendingPhotoStore(root / "state")

            store.remember(
                PendingPhoto(
                    chat_id=123,
                    message_id=456,
                    file_path=photo_path,
                    created_at=datetime.now(UTC) - timedelta(minutes=31),
                )
            )

            pending = store.get_recent(chat_id=123, ttl_minutes=30)

        self.assertIsNone(pending)

    def test_pending_photo_store_ignores_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            store = PendingPhotoStore(root / "state")

            store.remember(
                PendingPhoto(
                    chat_id=123,
                    message_id=456,
                    file_path=root / "missing.jpg",
                    created_at=datetime.now(UTC),
                )
            )

            pending = store.get_recent(chat_id=123, ttl_minutes=30)

        self.assertIsNone(pending)


if __name__ == "__main__":
    unittest.main()
