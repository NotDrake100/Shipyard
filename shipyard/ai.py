from __future__ import annotations

import asyncio
from pathlib import Path

from openai import OpenAI

from shipyard.config import Settings
from shipyard.media import image_to_data_url


class AIService:
    def __init__(self, settings: Settings, client: OpenAI | None = None) -> None:
        self._settings = settings
        self._client = client or OpenAI(api_key=settings.openai_api_key)

    async def transcribe_audio(self, audio_path: Path) -> str:
        return await asyncio.to_thread(self._transcribe_audio_sync, audio_path)

    async def describe_sketch(self, image_path: Path) -> str:
        return await asyncio.to_thread(self._describe_sketch_sync, image_path)

    def _transcribe_audio_sync(self, audio_path: Path) -> str:
        with audio_path.open("rb") as audio_file:
            result = self._client.audio.transcriptions.create(
                model=self._settings.transcription_model,
                file=audio_file,
            )

        text = getattr(result, "text", "")
        return text.strip()

    def _describe_sketch_sync(self, image_path: Path) -> str:
        result = self._client.chat.completions.create(
            model=self._settings.vision_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You describe product sketches for a software planning bot. "
                        "Focus on layout, UI elements, labels, data shown, user flows, "
                        "and any implementation-relevant details. Do not invent details."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Describe this sketch so a tech lead can turn it into a project plan.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": image_to_data_url(image_path)},
                        },
                    ],
                },
            ],
            max_tokens=700,
        )

        content = result.choices[0].message.content or ""
        return content.strip()
