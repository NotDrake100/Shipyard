from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from shipyard.config import Settings, load_settings


DEMO_CHAT_ID = 5231
DEMO_REQUEST_ID = "demo-broken-components"


def seed_demo(settings: Settings | None = None) -> Path:
    settings = settings or load_settings()
    request_dir = settings.inbox_dir / str(DEMO_CHAT_ID) / DEMO_REQUEST_ID
    sandbox_root = settings.worktree_root / f"{DEMO_CHAT_ID}-{DEMO_REQUEST_ID}"
    project_root = sandbox_root / "dummy-project"

    request_dir.mkdir(parents=True, exist_ok=True)
    sandbox_root.mkdir(parents=True, exist_ok=True)
    _write_dummy_project(project_root)

    tickets = _demo_tickets(sandbox_root)
    for ticket in tickets:
        worktree_path = Path(ticket["worktree"]["path"])
        worktree_path.mkdir(parents=True, exist_ok=True)
        _write_task(worktree_path, ticket)
        _write_thoughts(worktree_path, ticket)

    _write_json(
        request_dir / "request.json",
        {
            "request_id": DEMO_REQUEST_ID,
            "chat_id": DEMO_CHAT_ID,
            "created_at": _now(),
            "audio_path": None,
            "sketch_path": None,
            "transcript": "Create a demo UI project with a few broken components for Shipyard agents to fix.",
            "sketch_description": None,
        },
    )
    _write_json(
        request_dir / "plan.json",
        {
            "request_id": DEMO_REQUEST_ID,
            "project_name": "Broken UI Demo",
            "summary": "A small frontend demo with intentionally broken UI behavior.",
            "tech_stack": ["HTML", "CSS", "JavaScript"],
            "assumptions": ["No dashboard login is required for this demo."],
            "tickets": [
                {
                    "id": ticket["id"],
                    "title": ticket["title"],
                    "description": ticket["description"],
                    "file_paths": ticket["file_paths"],
                    "dependencies": ticket.get("dependencies", []),
                    "status": ticket["status"],
                }
                for ticket in tickets
            ],
            "created_at": _now(),
            "approved_at": _now(),
        },
    )
    _write_json(request_dir / "tickets.json", tickets)
    _write_json(sandbox_root / "worktrees.json", [ticket["worktree"] for ticket in tickets])
    return request_dir


def _demo_tickets(sandbox_root: Path) -> list[dict[str, Any]]:
    base = datetime.now(UTC)
    specs = [
        ("T001", "Create Dummy Project", "Create the simple broken UI demo without adding dashboard login.", "done", ["index.html", "styles.css", "app.js"]),
        ("T002", "Fix Dark Mode Icon", "The dark and light mode icon does not change when the theme changes.", "in_progress", ["app.js", "styles.css"]),
        ("T003", "Repair Theme Toggle", "The toggle changes text but does not update the page colors correctly.", "review", ["app.js"]),
        ("T004", "Fix Card Animation", "Sticky cards should move smoothly between columns instead of jumping.", "testing", ["styles.css", "app.js"]),
        ("T005", "Polish Broken Buttons", "Two buttons have labels but no working click behavior yet.", "ready", ["index.html", "app.js"]),
        ("T006", "Docs Setup", "Write simple notes explaining what was fixed and what is still broken.", "done", ["README.md"]),
    ]
    tickets = []
    for index, (ticket_id, title, description, status, files) in enumerate(specs):
        path = sandbox_root / ticket_id.lower()
        tickets.append(
            {
                "id": ticket_id,
                "title": title,
                "description": description,
                "file_paths": files,
                "dependencies": [] if index == 0 else [specs[index - 1][0]],
                "status": status,
                "due": (base + timedelta(days=index + 1)).strftime("%b %d"),
                "tag": _tag_for_status(status),
                "worktree": {
                    "ticket_id": ticket_id,
                    "ticket_title": title,
                    "branch": f"shipyard/demo/{ticket_id.lower()}",
                    "path": str(path),
                    "task_path": str(path / "TASK.md"),
                    "status": status,
                    "created_at": _now(),
                },
            }
        )
    return tickets


def _write_dummy_project(project_root: Path) -> None:
    project_root.mkdir(parents=True, exist_ok=True)
    (project_root / "index.html").write_text(
        """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Broken UI Demo</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <main class="app light">
    <header>
      <h1>Broken UI Demo</h1>
      <button id="theme">🌙 Dark mode</button>
    </header>
    <section class="cards">
      <article>Dark mode icon does not change.</article>
      <article>Theme colors do not fully switch.</article>
      <article>Card animation jumps instead of sliding.</article>
    </section>
    <button id="save">Save</button>
    <button id="share">Share</button>
  </main>
  <script src="app.js"></script>
</body>
</html>
""",
        encoding="utf-8",
    )
    (project_root / "styles.css").write_text(
        """.app { min-height: 100vh; padding: 32px; background: #fafafa; color: #111; transition: background .2s; }
.app.dark { background: #111; color: #fafafa; }
.cards { display: grid; gap: 14px; }
article { padding: 16px; background: #f8dc75; transition: none; }
button { padding: 10px 14px; margin: 8px; }
""",
        encoding="utf-8",
    )
    (project_root / "app.js").write_text(
        """const app = document.querySelector('.app');
const theme = document.querySelector('#theme');
theme.addEventListener('click', () => {
  app.classList.toggle('dark');
  // Broken on purpose: icon and label never change.
});
document.querySelector('#save').addEventListener('click', () => {});
document.querySelector('#share').addEventListener('click', () => {});
""",
        encoding="utf-8",
    )
    (project_root / "README.md").write_text(
        "# Broken UI Demo\n\nNo dashboard login. This project intentionally has broken theme and button behavior.\n",
        encoding="utf-8",
    )


def _write_task(path: Path, ticket: dict[str, Any]) -> None:
    (path / "TASK.md").write_text(
        f"""# {ticket["id"]}: {ticket["title"]}

## Goal
{ticket["description"]}

## Sandbox
This ticket has its own sandbox/worktree at `{path}`.

## Files
{chr(10).join(f"- `{file_path}`" for file_path in ticket["file_paths"])}
""",
        encoding="utf-8",
    )


def _write_thoughts(path: Path, ticket: dict[str, Any]) -> None:
    status = ticket["status"]
    if status == "done":
        text = "The agent finished this task. The work is ready to view in simple English."
    elif status == "in_progress":
        text = "The agent is working in this ticket sandbox now."
    elif status == "testing":
        text = "The agent has made changes and is running checks."
    elif status == "review":
        text = "The agent found a broken part and moved it to review."
    elif status == "ready":
        text = "The task is ready to ship after a quick check."
    else:
        text = "This task is waiting to start."
    (path / "THOUGHTS.md").write_text(f"# {ticket['title']}\n\n{text}\n", encoding="utf-8")


def _tag_for_status(status: str) -> str:
    return {
        "done": "Done",
        "in_progress": "Dev",
        "review": "Fix",
        "testing": "QA",
        "ready": "QA",
    }.get(status, "Task")


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def main() -> None:
    print(seed_demo())


if __name__ == "__main__":
    main()
