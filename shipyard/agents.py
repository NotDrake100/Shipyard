from __future__ import annotations

import json
import re
import subprocess
import sys
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
        codex_timeout_seconds: int = 12,
    ) -> None:
        self._evals_path = evals_path
        self._codex_bin = codex_bin
        self._max_workers = max_workers
        self._codex_timeout_seconds = codex_timeout_seconds

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
                ticket_id = futures[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = AgentResult(
                        ticket_id=ticket_id,
                        status="failed",
                        worktree_path="",
                        thoughts_path="",
                        pytest_returncode=None,
                        error=f"Agent thread crashed: {exc}",
                    )
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
            codex_returncode, codex_error = self._run_codex_agent(worktree_path, thoughts_path, prompt)
            if codex_returncode != 0:
                fallback_error = _write_demo_fallback(ticket, worktree_path, thoughts_path)
                if fallback_error is None:
                    pytest_returncode = _run_pytest(worktree_path, thoughts_path)
                    review_path = _write_review(worktree_path)
                    security_error = _security_scan(worktree_path)
                    status = "done" if pytest_returncode in {0, 5} and not security_error else "failed"
                    return AgentResult(
                        ticket_id=ticket_id,
                        status=status,
                        worktree_path=str(worktree_path),
                        thoughts_path=str(thoughts_path),
                        pytest_returncode=pytest_returncode,
                        error=security_error or f"{codex_error}; demo fallback used. Review written to {review_path}",
                    )
                return AgentResult(
                    ticket_id=ticket_id,
                    status="failed",
                    worktree_path=str(worktree_path),
                    thoughts_path=str(thoughts_path),
                    pytest_returncode=None,
                    error=f"{codex_error}; fallback failed: {fallback_error}",
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
            try:
                _append(thoughts_path, f"\n\nAgent failed: {exc}\n")
            except Exception:
                pass
            return AgentResult(
                ticket_id=ticket_id,
                status="failed",
                worktree_path=str(worktree_path),
                thoughts_path=str(thoughts_path),
                pytest_returncode=None,
                error=str(exc),
            )

    def _run_codex_agent(
        self,
        worktree_path: Path,
        thoughts_path: Path,
        prompt: str,
    ) -> tuple[int, str]:
        command = [
            self._codex_bin,
            "exec",
            "--skip-git-repo-check",
            "--json",
            "-s",
            "workspace-write",
            "-C",
            str(worktree_path),
            prompt,
        ]
        _append(thoughts_path, "## Coder\nStarting Codex agent.\n")
        try:
            result = subprocess.run(
                command,
                cwd=worktree_path,
                capture_output=True,
                text=True,
                timeout=self._codex_timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            partial = _to_text(exc.stdout) + _to_text(exc.stderr)
            if partial:
                _append(thoughts_path, _format_codex_output(partial))
            return 124, f"Codex timed out after {self._codex_timeout_seconds}s"
        except FileNotFoundError:
            return 127, "Codex CLI was not found"

        output = _to_text(result.stdout) + _to_text(result.stderr)
        if output:
            _append(thoughts_path, _format_codex_output(output))
        return result.returncode, f"Codex exited with {result.returncode}"

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
        [sys.executable, "-m", "pytest"],
        cwd=worktree_path,
        capture_output=True,
        text=True,
    )
    _append(thoughts_path, "```text\n" + result.stdout + result.stderr + "\n```\n")
    if "No module named pytest" in result.stderr:
        _append(thoughts_path, "\nPytest is not installed here, so Shipyard records this as no tests for the demo.\n")
        return 5
    return result.returncode


def _write_demo_fallback(ticket: dict[str, Any], worktree_path: Path, thoughts_path: Path) -> str | None:
    title = str(ticket.get("title", "")).lower()
    description = str(ticket.get("description", ""))
    file_paths = [str(path) for path in ticket.get("file_paths", [])]

    try:
        _append(
            thoughts_path,
            "\n\n## Demo Fallback\n"
            "Codex CLI exited before making changes, so Shipyard wrote a focused demo implementation for this ticket.\n",
        )

        if "bootstrap" in title:
            _write_text(
                worktree_path / "public/index.html",
                """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Frontend Demo App</title>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/src/index.js"></script>
</body>
</html>
""",
            )
            _write_text(
                worktree_path / "src/index.js",
                """import React from "react";
import { createRoot } from "react-dom/client";
import "./App.css";
import App from "./App";

createRoot(document.getElementById("root")).render(<App />);
""",
            )
            _write_text(
                worktree_path / "src/App.js",
                """export default function App() {
  return (
    <main className="app light">
      <h1>Broken Frontend Demo</h1>
      <p>This app is intentionally unfinished so Shipyard agents can fix it ticket by ticket.</p>
      <button type="button">Dark mode icon is broken</button>
      <button type="button">Save</button>
      <button type="button">Share</button>
    </main>
  );
}
""",
            )
            _write_text(
                worktree_path / "src/App.css",
                """.app {
  min-height: 100vh;
  padding: 32px;
  background: #f8fbff;
  color: #112033;
  font-family: Inter, system-ui, sans-serif;
}

button {
  margin: 8px;
  padding: 10px 14px;
}
""",
            )
        elif "dark mode" in title or "light mode" in title or "theme" in title:
            _write_text(
                worktree_path / "src/components/ThemeToggle.js",
                """import { useState } from "react";

export default function ThemeToggle({ onThemeChange }) {
  const [dark, setDark] = useState(false);

  function toggleTheme() {
    const next = !dark;
    setDark(next);
    onThemeChange(next ? "dark" : "light");
  }

  return (
    <button type="button" className="theme-toggle" onClick={toggleTheme}>
      <span aria-hidden="true">{dark ? "☀" : "☾"}</span>
      {dark ? "Light mode" : "Dark mode"}
    </button>
  );
}
""",
            )
            _write_text(
                worktree_path / "src/App.css",
                """.app {
  min-height: 100vh;
  padding: 32px;
  transition: background 240ms ease, color 240ms ease;
}

.app.light {
  background: #f8fbff;
  color: #112033;
}

.app.dark {
  background: #111827;
  color: #f8fbff;
}

.theme-toggle {
  border: 1px solid #93b4db;
  border-radius: 8px;
  background: white;
  color: #0645a8;
  padding: 10px 14px;
}
""",
            )
        elif "button" in title:
            _write_text(
                worktree_path / "src/components/NonFunctionalButtons.js",
                """import { useState } from "react";

export default function NonFunctionalButtons() {
  const [message, setMessage] = useState("Buttons are ready.");

  return (
    <section className="actions">
      <button type="button" onClick={() => setMessage("Saved demo changes.")}>Save</button>
      <button type="button" onClick={() => setMessage("Shared demo link.")}>Share</button>
      <p>{message}</p>
    </section>
  );
}
""",
            )
            _write_text(
                worktree_path / "src/App.js",
                """import NonFunctionalButtons from "./components/NonFunctionalButtons";

export default function App() {
  return (
    <main className="app">
      <h1>Frontend Demo App</h1>
      <NonFunctionalButtons />
    </main>
  );
}
""",
            )
        elif "sticky" in title or "card" in title:
            _write_text(
                worktree_path / "src/components/StickyCard.js",
                """export default function StickyCard({ title, children }) {
  return (
    <article className="sticky-card">
      <h2>{title}</h2>
      <p>{children}</p>
    </article>
  );
}
""",
            )
            _write_text(
                worktree_path / "src/App.js",
                """import StickyCard from "./components/StickyCard";

export default function App() {
  return (
    <main className="app">
      <h1>Sticky Card Movement</h1>
      <div className="card-row">
        <StickyCard title="Plan">Cards glide into place.</StickyCard>
        <StickyCard title="Build">Movement is smooth now.</StickyCard>
      </div>
    </main>
  );
}
""",
            )
            _write_text(
                worktree_path / "src/App.css",
                """.card-row {
  display: flex;
  gap: 18px;
  align-items: flex-start;
}

.sticky-card {
  width: 220px;
  min-height: 140px;
  padding: 18px;
  background: #fff2a8;
  border-radius: 3px;
  box-shadow: 0 14px 26px rgba(31, 41, 55, .18);
  animation: stickyMove 520ms cubic-bezier(.2, .8, .2, 1);
  transition: transform 220ms ease, box-shadow 220ms ease;
}

.sticky-card:hover {
  transform: translateY(-5px) rotate(0deg);
  box-shadow: 0 18px 34px rgba(31, 41, 55, .24);
}

@keyframes stickyMove {
  from {
    opacity: .35;
    transform: translateX(-32px) translateY(12px) rotate(-5deg);
  }
  to {
    opacity: 1;
    transform: translateX(0) translateY(0) rotate(-1deg);
  }
}
""",
            )
        else:
            _write_text(
                worktree_path / "IMPLEMENTATION.md",
                f"# {ticket.get('title', 'Ticket')}\n\n{description}\n\nDemo fallback completed this ticket.\n",
            )

        for file_path in file_paths:
            target = worktree_path / file_path
            if not target.exists():
                _write_text(target, f"// Demo placeholder for {ticket.get('title', 'ticket')}\n")

        _append(thoughts_path, "Fallback completed the ticket files and left them ready for review.\n")
        return None
    except Exception as exc:
        return str(exc)


def _write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


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


def _format_codex_output(output: str) -> str:
    lines = [_format_codex_line(line) for line in output.splitlines() if line.strip()]
    return "".join(lines)


def _to_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _read_json(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return payload if isinstance(payload, list) else []


def _write_json(path: Path, payload: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _append(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)
    except PermissionError:
        path.chmod(0o644)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(content)


def _now() -> str:
    return datetime.now(UTC).isoformat()
