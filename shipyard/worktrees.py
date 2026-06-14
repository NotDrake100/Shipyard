from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shipyard.planning import ProjectPlan, Ticket


@dataclass(frozen=True)
class TicketWorktree:
    ticket_id: str
    ticket_title: str
    branch: str
    path: str
    task_path: str
    status: str
    created_at: str


class WorktreeManager:
    def __init__(self, repo_root: Path, worktree_root: Path) -> None:
        self._repo_root = repo_root
        self._worktree_root = worktree_root

    def create_for_plan(self, chat_id: int, plan: ProjectPlan) -> list[TicketWorktree]:
        self._worktree_root.mkdir(parents=True, exist_ok=True)
        project_slug = _slug(plan.project_name or plan.request_id)
        request_root = self._worktree_root / f"{chat_id}-{_slug(plan.request_id)}"
        request_root.mkdir(parents=True, exist_ok=True)
        project_repo = request_root / f"{project_slug}-repo"
        self._ensure_project_repo(project_repo, plan)

        records = [
            self._create_project_worktree(project_repo, request_root, project_slug, plan, ticket)
            for ticket in plan.tickets
        ]

        self._write_json(request_root / "worktrees.json", [asdict(record) for record in records])
        return records

    def _ensure_project_repo(self, project_repo: Path, plan: ProjectPlan) -> None:
        project_repo.mkdir(parents=True, exist_ok=True)
        if (project_repo / ".git").exists():
            return

        _git(["init", "-b", "main"], project_repo, check=False)
        if not (project_repo / ".git").exists():
            _git(["init"], project_repo)
            _git(["checkout", "-B", "main"], project_repo)

        _git(["config", "user.name", "Shipyard Bot"], project_repo)
        _git(["config", "user.email", "shipyard@example.local"], project_repo)

        (project_repo / "README.md").write_text(_project_readme(plan), encoding="utf-8")
        (project_repo / ".gitignore").write_text(
            ".env\nnode_modules/\n.venv/\n__pycache__/\n.pytest_cache/\ndist/\nbuild/\n",
            encoding="utf-8",
        )
        _git(["add", "."], project_repo)
        _git(["commit", "-m", "Initial project repo"], project_repo)

    def _create_project_worktree(
        self,
        project_repo: Path,
        request_root: Path,
        project_slug: str,
        plan: ProjectPlan,
        ticket: Ticket,
    ) -> TicketWorktree:
        branch = f"shipyard/{project_slug}/{_slug(plan.request_id)}/{_slug(ticket.id)}"
        path = request_root / _slug(ticket.id)

        if path.exists() and not (path / ".git").exists():
            shutil.rmtree(path)
        if not path.exists():
            _git(["worktree", "add", "-B", branch, str(path), "main"], project_repo)

        task_path = path / "TASK.md"
        task_path.write_text(_task_markdown(plan, ticket), encoding="utf-8")
        return _record(ticket, branch, path, task_path)

    def _is_git_repo(self) -> bool:
        result = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=self._repo_root,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0 and result.stdout.strip() == "true"

    def _write_json(self, path: Path, payload: Any) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)


def enrich_tickets_with_worktrees(tickets_path: Path, records: list[TicketWorktree]) -> None:
    if not tickets_path.exists():
        return

    records_by_ticket = {record.ticket_id: asdict(record) for record in records}
    with tickets_path.open("r", encoding="utf-8") as handle:
        tickets = json.load(handle)

    for ticket in tickets:
        record = records_by_ticket.get(str(ticket.get("id")))
        if record:
            ticket["worktree"] = record
            ticket["status"] = "todo"

    with tickets_path.open("w", encoding="utf-8") as handle:
        json.dump(tickets, handle, indent=2, sort_keys=True)


def _record(ticket: Ticket, branch: str, path: Path, task_path: Path) -> TicketWorktree:
    return TicketWorktree(
        ticket_id=ticket.id,
        ticket_title=ticket.title,
        branch=branch,
        path=str(path),
        task_path=str(task_path),
        status="ready",
        created_at=datetime.now(UTC).isoformat(),
    )


def _task_markdown(plan: ProjectPlan, ticket: Ticket) -> str:
    dependencies = ", ".join(ticket.dependencies) if ticket.dependencies else "None"
    files = "\n".join(f"- `{file_path}`" for file_path in ticket.file_paths) or "- TBD"
    stack = ", ".join(plan.tech_stack) if plan.tech_stack else "Use the project-appropriate stack."

    return f"""# {ticket.id}: {ticket.title}

## Project
{plan.project_name}

## Project Summary
{plan.summary}

## Suggested Stack
{stack}

## Ticket Description
{ticket.description}

## Expected Files
{files}

## Dependencies
{dependencies}

## Agent Instructions
- Implement only this ticket's scope.
- Keep changes focused and easy to review.
- Add or update tests when practical.
- Write progress notes to `THOUGHTS.md`.
"""


def _project_readme(plan: ProjectPlan) -> str:
    stack = ", ".join(plan.tech_stack) if plan.tech_stack else "To be decided by Shipyard agents"
    tickets = "\n".join(f"- {ticket.id}: {ticket.title}" for ticket in plan.tickets)
    return f"""# {plan.project_name}

{plan.summary}

## Stack
{stack}

## Shipyard Tickets
{tickets}
"""


def _git(args: list[str], cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=check,
        capture_output=True,
        text=True,
    )


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:80] or "item"
