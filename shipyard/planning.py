from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from openai import OpenAI

from shipyard.config import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Ticket:
    id: str
    title: str
    description: str
    file_paths: list[str]
    dependencies: list[str] = field(default_factory=list)
    status: str = "todo"


@dataclass(frozen=True)
class ProjectPlan:
    request_id: str
    project_name: str
    summary: str
    tech_stack: list[str]
    assumptions: list[str]
    tickets: list[Ticket]
    created_at: str
    approved_at: str | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, payload: dict[str, Any]) -> "ProjectPlan":
        tickets = [Ticket(**ticket) for ticket in payload.get("tickets", [])]
        return cls(
            request_id=str(payload["request_id"]),
            project_name=str(payload.get("project_name") or "Untitled Project"),
            summary=str(payload.get("summary") or ""),
            tech_stack=_string_list(payload.get("tech_stack")),
            assumptions=_string_list(payload.get("assumptions")),
            tickets=tickets,
            created_at=str(payload.get("created_at") or datetime.now(UTC).isoformat()),
            approved_at=payload.get("approved_at"),
        )

    @classmethod
    def from_model_payload(cls, request_id: str, payload: dict[str, Any]) -> "ProjectPlan":
        tickets = [
            _ticket_from_payload(index, ticket)
            for index, ticket in enumerate(payload.get("tickets") or [], start=1)
            if isinstance(ticket, dict)
        ]
        if not tickets:
            tickets = [
                Ticket(
                    id="T001",
                    title="Create initial project scaffold",
                    description="Set up the initial repository structure for the requested project.",
                    file_paths=["README.md"],
                    dependencies=[],
                )
            ]

        return cls(
            request_id=request_id,
            project_name=str(payload.get("project_name") or "Untitled Project"),
            summary=str(payload.get("summary") or ""),
            tech_stack=_string_list(payload.get("tech_stack")),
            assumptions=_string_list(payload.get("assumptions")),
            tickets=tickets[:12],
            created_at=datetime.now(UTC).isoformat(),
        )

    def approved(self) -> "ProjectPlan":
        return ProjectPlan(
            request_id=self.request_id,
            project_name=self.project_name,
            summary=self.summary,
            tech_stack=self.tech_stack,
            assumptions=self.assumptions,
            tickets=self.tickets,
            created_at=self.created_at,
            approved_at=datetime.now(UTC).isoformat(),
        )


class PlanningService:
    def __init__(self, settings: Settings, client: OpenAI | None = None) -> None:
        self._settings = settings
        self._client = client or OpenAI(api_key=settings.openai_api_key)

    async def generate_plan(self, intake_payload: dict[str, Any]) -> ProjectPlan:
        return await asyncio.to_thread(self._generate_plan_sync, intake_payload)

    def _generate_plan_sync(self, intake_payload: dict[str, Any]) -> ProjectPlan:
        try:
            result = self._client.chat.completions.create(
                model=self._settings.planning_model,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are Shipyard's technical lead. Turn messy multimodal user input "
                            "into a practical software project plan. Return only JSON with keys: "
                            "project_name, summary, tech_stack, assumptions, tickets. Each ticket "
                            "must have id, title, description, file_paths, dependencies. Tickets "
                            "must be ordered, atomic, implementation-ready, and dependency-aware. "
                            "If this appears to be a brand-new project, include an initial bootstrap "
                            "ticket before feature tickets."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(_planner_input(intake_payload), indent=2),
                    },
                ],
                max_tokens=2500,
            )

            raw_content = result.choices[0].message.content or "{}"
            model_payload = json.loads(raw_content)
            return ProjectPlan.from_model_payload(str(intake_payload["request_id"]), model_payload)
        except Exception:
            logger.exception("Planning model failed; using fallback project plan")
            return fallback_plan(intake_payload)


class PlanStore:
    def __init__(self, inbox_dir: Path) -> None:
        self._inbox_dir = inbox_dir

    def save_plan(self, chat_id: int, plan: ProjectPlan) -> None:
        self._write_json(self._plan_path(chat_id, plan.request_id), plan.to_json())

    def get_plan(self, chat_id: int, request_id: str) -> ProjectPlan:
        with self._plan_path(chat_id, request_id).open("r", encoding="utf-8") as handle:
            return ProjectPlan.from_json(json.load(handle))

    def approve_plan(self, chat_id: int, request_id: str) -> ProjectPlan:
        plan = self.get_plan(chat_id, request_id).approved()
        self.save_plan(chat_id, plan)
        self._write_json(
            self._tickets_path(chat_id, request_id),
            [ticket.__dict__ for ticket in plan.tickets],
        )
        return plan

    def tickets_path(self, chat_id: int, request_id: str) -> Path:
        return self._tickets_path(chat_id, request_id)

    def tickets_payload(self, chat_id: int, request_id: str) -> list[dict[str, Any]]:
        path = self._tickets_path(chat_id, request_id)
        if not path.exists():
            return []
        with path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        return payload if isinstance(payload, list) else []

    def save_tickets_payload(
        self,
        chat_id: int,
        request_id: str,
        tickets: list[dict[str, Any]],
    ) -> None:
        self._write_json(self._tickets_path(chat_id, request_id), tickets)

    def request_payload(self, chat_id: int, request_id: str) -> dict[str, Any]:
        with self._request_path(chat_id, request_id).open("r", encoding="utf-8") as handle:
            return json.load(handle)

    def save_request_payload(self, chat_id: int, request_id: str, payload: dict[str, Any]) -> None:
        self._write_json(self._request_path(chat_id, request_id), payload)

    def _request_dir(self, chat_id: int, request_id: str) -> Path:
        return self._inbox_dir / str(chat_id) / request_id

    def _request_path(self, chat_id: int, request_id: str) -> Path:
        return self._request_dir(chat_id, request_id) / "request.json"

    def _plan_path(self, chat_id: int, request_id: str) -> Path:
        return self._request_dir(chat_id, request_id) / "plan.json"

    def _tickets_path(self, chat_id: int, request_id: str) -> Path:
        return self._request_dir(chat_id, request_id) / "tickets.json"

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)


def _planner_input(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_id": payload.get("request_id"),
        "text_or_transcript": payload.get("transcript") or "",
        "sketch_description": payload.get("sketch_description") or "",
        "has_audio": bool(payload.get("audio_path")),
        "has_sketch": bool(payload.get("sketch_path")),
    }


def fallback_plan(payload: dict[str, Any]) -> ProjectPlan:
    request_id = str(payload.get("request_id") or "request")
    text = str(payload.get("transcript") or "").strip()
    has_sketch = bool(payload.get("sketch_path"))
    summary_parts = []
    if text:
        summary_parts.append(text)
    if has_sketch:
        summary_parts.append("Includes a sketch/photo reference.")
    summary = " ".join(summary_parts) or "Build the project described by the user."

    return ProjectPlan.from_model_payload(
        request_id,
        {
            "project_name": _fallback_project_name(text),
            "summary": summary,
            "tech_stack": ["Python", "Flask", "HTML/CSS/JavaScript"],
            "assumptions": [
                "This fallback plan was generated locally because the planning model failed.",
                "The user can refine tickets after approval.",
            ],
            "tickets": [
                {
                    "id": "T001",
                    "title": "Bootstrap project scaffold",
                    "description": "Create the initial repository structure, README, app entrypoint, and dependency file.",
                    "file_paths": ["README.md", "pyproject.toml", "app.py"],
                    "dependencies": [],
                },
                {
                    "id": "T002",
                    "title": "Implement core user flow",
                    "description": "Build the main workflow described in the intake request.",
                    "file_paths": ["app.py", "templates/index.html", "static/app.js"],
                    "dependencies": ["T001"],
                },
                {
                    "id": "T003",
                    "title": "Polish UI and validation",
                    "description": "Add basic styling, empty states, input validation, and user-facing error handling.",
                    "file_paths": ["static/styles.css", "app.py"],
                    "dependencies": ["T002"],
                },
            ],
        },
    )


def _fallback_project_name(text: str) -> str:
    words = [word.strip(".,:;!?()[]{}") for word in text.split()[:5]]
    words = [word.capitalize() for word in words if word]
    return " ".join(words) or "Shipyard Project"


def _ticket_from_payload(index: int, payload: dict[str, Any]) -> Ticket:
    ticket_id = str(payload.get("id") or f"T{index:03d}").upper().replace(" ", "-")
    return Ticket(
        id=ticket_id,
        title=str(payload.get("title") or f"Ticket {index}"),
        description=str(payload.get("description") or ""),
        file_paths=_string_list(payload.get("file_paths") or payload.get("file_path")),
        dependencies=_string_list(payload.get("dependencies")),
    )


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    return [str(value)]
