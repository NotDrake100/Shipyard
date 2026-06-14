# Shipyard

Shipyard is a Telegram-controlled AI project factory. Send a text, voice note, or sketch photo to the bot; it turns the idea into a project plan, creates implementation tickets, gives every ticket its own sandbox/worktree, runs Codex agents, and shows everything on a live Shipyard Kanban board.

## Hackathon Demo

Shipyard demonstrates:

- Telegram multimodal intake: text, voice/audio, photo/sketch, or combinations.
- OpenAI planning: a structured project plan and atomic tickets.
- Multi-agent execution: each ticket gets a separate sandbox under `/tmp/shipyard`.
- Live Kanban: sticky notes move across `To Do`, `In Progress`, `Review`, `Testing`, `Ready To Ship`, and `Done`.
- Demo project: a small broken UI website with issues like dark/light mode icon not updating, theme toggle bugs, card animation bugs, and broken buttons.

No dashboard login is required.

## Build Directions

Shipyard is designed to fit every hackathon direction:

- **Agentic Coding:** Shipyard turns a Telegram request into a structured plan, implementation tickets, isolated git worktrees, Codex agent runs, tests, review, security checks, retry, and merge flow.
- **UX for Agentic Applications:** Telegram becomes the lightweight command center while the live Kanban board makes agent work visible as sticky notes moving through the delivery pipeline.
- **Multimodal Intelligence:** Users can describe a project with text, voice/audio, photo/sketch, or combinations. Shipyard transcribes audio, describes sketches, and merges all input into one project plan.
- **Domain Agents:** Coder, tester, reviewer, and security agents operate inside real software constraints: git sandboxes, file diffs, test commands, review notes, security warnings, and user approvals.
- **Building Evals:** Agent outcomes are logged to JSONL and summarized in an eval dashboard with success rate, ticket status, and recent run details.

## Setup

```bash
git clone https://github.com/NotDrake100/Shipyard.git
cd Shipyard
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

Fill in `.env` locally:

```env
TELEGRAM_BOT_TOKEN=your_botfather_token
OPENAI_API_KEY=your_openai_api_key
SHIPYARD_STORAGE_DIR=data
OPENAI_TRANSCRIPTION_MODEL=whisper-1
OPENAI_VISION_MODEL=gpt-4o-mini
OPENAI_PLANNING_MODEL=gpt-4o-mini
PENDING_PHOTO_TTL_MINUTES=30
TELEGRAM_NETWORK_TIMEOUT_SECONDS=60
SHIPYARD_WORKTREE_ROOT=/tmp/shipyard
SHIPYARD_ENABLE_SERVER=true
SHIPYARD_SERVER_HOST=127.0.0.1
SHIPYARD_SERVER_PORT=5050
```

Do not commit `.env`. It is ignored by git.

## Run The Demo

Seed the demo broken-components project:

```bash
python -m shipyard.demo_seed
```

Start the board:

```bash
python -m shipyard.server
```

Open:

```text
http://shipyard.localhost:5050
```

In another terminal, start the Telegram bot:

```bash
source .venv/bin/activate
python -m shipyard.bot
```

## What To Type In Telegram

From your phone, send this to `ShipyardBot`:

```text
Build a small frontend demo app with broken components. It should have a dark mode and light mode toggle where the icon is broken, two buttons that do not work, and sticky card movement that needs fixing. Do not build a dashboard login. Make separate tickets so Shipyard agents can fix each issue in isolated sandboxes.
```

Then:

1. Wait for the project plan.
2. Tap `Approve & Start`.
3. Watch the board at `http://shipyard.localhost:5050`.
4. Done cards have a `View` button with simple-English details.

## Commands

```bash
python -m shipyard.bot        # Telegram bot + board server
python -m shipyard.server     # Board server only
python -m shipyard.demo_seed  # Seed demo tickets and broken project
pytest                       # Run tests
```

## Architecture

```text
Telegram text/voice/photo
  -> media download and transcription
  -> optional sketch description
  -> planning model creates project plan and tickets
  -> Approve & Start
  -> git worktree/sandbox per ticket under /tmp/shipyard
  -> Codex runner per ticket
  -> THOUGHTS.md, REVIEW.md, SECURITY.md, tickets.json
  -> live Flask Kanban board
```

## Security

- `.env` is ignored.
- Never paste API keys into Telegram or commits.
- If a key was accidentally shown in a screenshot or chat, rotate it before submitting.
