from __future__ import annotations

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class AgentResult:
    ticket_id: str
    status: str
    worktree_path: str
    thoughts_path: str
    pytest_returncode: int | None
    error: str | None = None


class AgentRunner:
    def __init__(
        self,
        evals_path: Path,
        codex_bin: str = "codex",
        max_workers: int = 3,
    ) -> None:
        self._evals_path = evals_path
        self._codex_bin = codex_bin
        self._max_workers = max_workers

    def run_for_tickets_file(self, tickets_path: Path) -> list[AgentResult]:
        tickets = _read_json(tickets_path)
        runnable = [ticket for ticket in tickets if ticket.get("worktree")]
        return self.run_ticket_payloads(tickets_path, runnable)

    def run_ticket_payloads(
        self,
        tickets_path: Path,
        runnable: list[dict[str, Any]],
    ) -> list[AgentResult]:
        if not runnable:
            return []

        self._set_statuses(tickets_path, {str(ticket["id"]): "in_progress" for ticket in runnable})

        results: list[AgentResult] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as executor:
            futures = {
                executor.submit(self._run_one_ticket, ticket): str(ticket["id"])
                for ticket in runnable
            }
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                self._set_statuses(tickets_path, {result.ticket_id: result.status})
                self._append_eval(result)

        return results

    def _run_one_ticket(self, ticket: dict[str, Any]) -> AgentResult:
        ticket_id = str(ticket["id"])
        worktree_path = Path(str(ticket["worktree"]["path"]))
        thoughts_path = worktree_path / "THOUGHTS.md"
        task_path = worktree_path / "TASK.md"

        try:
            _append(thoughts_path, f"# Thoughts for {ticket_id}\n\nStarted: {_now()}\n\n")
            prompt = _agent_prompt(task_path)
            process = subprocess.Popen(
                [
                    self._codex_bin,
                    "exec",
                    "--skip-git-repo-check",
                    "--json",
                    "-a",
                    "never",
                    "-s",
                    "workspace-write",
                    "-C",
                    str(worktree_path),
                    prompt,
                ],
                cwd=worktree_path,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            assert process.stdout is not None
            for line in process.stdout:
                _append(thoughts_path, _format_codex_line(line))

            codex_returncode = process.wait()
            if codex_returncode != 0:
                return AgentResult(
                    ticket_id=ticket_id,
                    status="failed",
                    worktree_path=str(worktree_path),
                    thoughts_path=str(thoughts_path),
                    pytest_returncode=None,
                    error=f"Codex exited with {codex_returncode}",
                )

            pytest_returncode = _run_pytest(worktree_path, thoughts_path)
            review_path = _write_review(worktree_path)
            security_error = _security_scan(worktree_path)
            if security_error:
                _append(thoughts_path, f"\n\n## Security\n{security_error}\n")
            status = "done" if pytest_returncode in {0, 5} and not security_error else "failed"
            return AgentResult(
                ticket_id=ticket_id,
                status=status,
                worktree_path=str(worktree_path),
                thoughts_path=str(thoughts_path),
                pytest_returncode=pytest_returncode,
                error=security_error or f"Review written to {review_path}",
            )
        except Exception as exc:
            _append(thoughts_path, f"\n\nAgent failed: {exc}\n")
            return AgentResult(
                ticket_id=ticket_id,
                status="failed",
                worktree_path=str(worktree_path),
                thoughts_path=str(thoughts_path),
                pytest_returncode=None,
                error=str(exc),
            )

    def _set_statuses(self, tickets_path: Path, statuses: dict[str, str]) -> None:
        tickets = _read_json(tickets_path)
        for ticket in tickets:
            ticket_id = str(ticket.get("id"))
            if ticket_id in statuses:
                ticket["status"] = statuses[ticket_id]
                if ticket.get("worktree"):
                    ticket["worktree"]["status"] = statuses[ticket_id]
        _write_json(tickets_path, tickets)

    def _append_eval(self, result: AgentResult) -> None:
        payload = {
            "event": "agent_result",
            "ticket_id": result.ticket_id,
            "status": result.status,
            "worktree_path": result.worktree_path,
            "thoughts_path": result.thoughts_path,
            "pytest_returncode": result.pytest_returncode,
            "error": result.error,
            "created_at": _now(),
        }
        self._evals_path.parent.mkdir(parents=True, exist_ok=True)
        with self._evals_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True) + "\n")


def _agent_prompt(task_path: Path) -> str:
    return (
        "You are the Shipyard Coder Agent. Read TASK.md and implement only that ticket. "
        "Keep changes focused. Write a concise THOUGHTS.md update as you work. "
        "Do not ask questions; make reasonable assumptions for a demo MVP.\n\n"
        + task_path.read_text(encoding="utf-8")
    )


def _run_pytest(worktree_path: Path, thoughts_path: Path) -> int:
    _append(thoughts_path, "\n\n## Tester\nRunning pytest once.\n\n")
    result = subprocess.run(
        ["python", "-m", "pytest"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    _append(thoughts_path, "```text\n" + result.stdout + result.stderr + "\n```\n")
    return result.returncode


def _write_review(worktree_path: Path) -> Path:
    review_path = worktree_path / "REVIEW.md"
    diff_stat = subprocess.run(
        ["git", "diff", "--stat"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    diff_short = subprocess.run(
        ["git", "diff", "--", "."],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    review_path.write_text(
        "# Review\n\n"
        "Automated demo review completed.\n\n"
        "## Diff Stat\n\n```text\n"
        + (diff_stat.stdout or "(no diff stat)")
        + "\n```\n\n## Notes\n"
        + _review_notes(diff_short.stdout),
        encoding="utf-8",
    )
    return review_path


def _review_notes(diff: str) -> str:
    if not diff.strip():
        return "- No code changes detected.\n"
    notes = ["- Diff exists and is ready for human review."]
    if "TODO" in diff or "FIXME" in diff:
        notes.append("- TODO/FIXME found; check before merging.")
    return "\n".join(notes) + "\n"


def _security_scan(worktree_path: Path) -> str | None:
    diff = subprocess.run(
        ["git", "diff", "--", "."],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    ).stdout
    patterns = [
        r"sk-[A-Za-z0-9_-]{20,}",
        r"(?i)(api[_-]?key|secret|password)\s*=\s*['\"][^'\"]+['\"]",
        r"(?i)telegram_bot_token\s*=",
    ]
    for pattern in patterns:
        if re.search(pattern, diff):
            security_path = worktree_path / "SECURITY.md"
            security_path.write_text(
                "# Security Warning\n\nPotential secret or risky credential pattern found in diff.\n",
                encoding="utf-8",
            )
            return f"Potential secret or credential pattern found. See {security_path}."
    return None


def _format_codex_line(line: str) -> str:
    try:
        payload = json.loads(line)
    except json.JSONDecodeError:
        return line

    message = payload.get("message") or payload.get("text") or payload.get("type") or payload
    return f"- {message}\n"


def _read_json(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, list) else []


def _write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _append(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(content)


def _now() -> str:
    return datetime.now(UTC).isoformat()
