# ⚓ Shipyard

**Don't Just Build it - Ship It**

Shipyard is a Telegram‑controlled AI project factory. Send a text, voice note, or sketch photo to the bot — it turns the idea into a project plan, creates implementation tickets, gives every ticket its own sandbox/worktree, runs Codex agents, and shows everything on a live Kanban board.

Built solo with Codex in 7 hours for the Codex Hackathon, Pune 2026.

---

## 🎥 What Shipyard Does

1. **You speak (or type, or sketch).** Send a project idea to the Telegram bot as text, a voice note, a photo of a hand‑drawn wireframe, or all three at once.
2. **Shipyard plans.** A Codex‑powered tech lead generates a structured project plan with ordered, atomic tickets and dependency tracking.
3. **You approve.** The plan arrives in Telegram with an **Approve & Start** button. You stay in control.
4. **Agents build in parallel.** Each ticket gets its own isolated git worktree under `/tmp/shipyard`. Multiple tickets run simultaneously.
5. **Tests gate everything.** A tester agent runs your real test suite. If something fails, the agent retries with the failure context until it passes.
6. **You merge from your phone.** Only verified, tested code gets a **Merge** button. One tap, done.
7. **Live transparency.** A Kanban board shows sticky‑note cards moving through columns, with each agent's live thoughts scrolling inside the card.
8. **Evals track improvement.** Every run is logged; a dashboard shows success rate, cost, and time.

---

## 🏆 Hackathon Category Fit

Shipyard covers all five build directions:

- **Agentic Coding** — Codex agents implement tickets in isolated sandboxes with planning, execution, testing, review, security checks, retry, and merge flow.
- **UX for Agentic Applications** — Telegram is the lightweight command center; the live Kanban board makes agent work visible as sticky notes moving through the delivery pipeline.
- **Multimodal Intelligence** — Users describe projects with text, voice/audio, photo/sketch, or combinations. Whisper transcribes, a vision model describes sketches, and all input merges into one plan.
- **Domain Agents** — Coder, tester, reviewer, and security agents operate inside real software constraints: git sandboxes, file diffs, test commands, review notes, security warnings, and user approvals.
- **Building Evals** — Agent outcomes are logged to JSONL and summarized in an eval dashboard with success rate, ticket status, and recent run details.

---

## 🧱 Architecture

```
Telegram (text / voice / photo)
→ media download
→ Whisper transcription (voice)
→ Vision description (photo/sketch)
→ Planning model creates project plan + atomic tickets
→ Approve & Start button in Telegram
→ Git worktree sandbox per ticket under /tmp/shipyard
→ Codex runner per ticket (coder → tester → reviewer → security)
→ Artifacts: THOUGHTS.md, REVIEW.md, SECURITY.md, tickets.json
→ Live Flask Kanban board with sticky-note cards
→ JSONL evals log → /evals-dashboard with Chart.js
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.11+
- A Telegram bot token from [BotFather](https://t.me/botfather)
- An OpenAI API key from [platform.openai.com](https://platform.openai.com)
- Git installed on your machine

### Installation

```bash
git clone https://github.com/NotDrake100/Shipyard.git
cd Shipyard
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

### Configuration

Fill in `.env` with your keys:

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

Do not commit `.env` — it is git‑ignored.

---

## 🎬 Run The Demo

### 1. Seed the demo broken‑components project

```bash
python -m shipyard.demo_seed
```

This creates a small React app with intentionally broken features:

- Dark/light mode toggle with broken icon
- Two non‑functional buttons
- Sticky card movement that needs fixing

### 2. Start the Kanban board

```bash
python -m shipyard.server
```

Open your browser to:

```
http://localhost:5050
```

### 3. Start the Telegram bot

In another terminal:

```bash
source .venv/bin/activate
python -m shipyard.bot
```

### 4. Send your project idea

From your phone, open Telegram and send this message to your bot:

```
Build a small frontend demo app with broken components. It should have a dark mode and light mode toggle where the icon is broken, two buttons that do not work, and sticky card movement that needs fixing. Do not build a dashboard login. Make separate tickets so Shipyard agents can fix each issue in isolated sandboxes.
```

### 5. Watch Shipyard work

- The bot replies with a project plan — review it.
- Tap **Approve & Start**.
- Watch the Kanban board at `http://localhost:5050` as sticky notes move through columns:

  `To Do → In Progress → Review → Testing → Ready To Ship → Done`

- Each card shows the agent's live thoughts as it works.
- Click any **Done** card to see a simple‑English summary of what was built.
- Send `/evals` to the bot to see success rate and stats.
- Open `/evals-dashboard` on the board for charts.

---

## 📋 Commands Reference

| Command | What it does |
|---|---|
| `/start` | Initialize the bot, get welcome message |
| `/help` | Show available commands |
| `/evals` | Get a summary of all agent runs (success rate, time, cost) |
| Text message | Send a project idea as text |
| Voice note | Send a project idea as audio (Whisper transcribes) |
| Photo/Sketch | Send a wireframe or UI sketch (vision model describes) |
| Voice + Photo | Combine both for multimodal input |

---

## 🎨 Kanban Board Reference

| Column | Meaning | Card Behavior |
|---|---|---|
| To Do | Ticket created, waiting for an agent | Static, grey border |
| In Progress | Agent is writing code | Pulsing blue border, thoughts scrolling |
| Review | Reviewer agent inspecting the diff | Yellow border, review notes appear |
| Testing | Tester running pytest | Orange border, test output scrolling |
| Ready To Ship | All gates passed, merge ready | Green border, Merge button visible |
| Done | Code merged | Green card, click for summary |

Cards animate smoothly between columns. Click any card to expand and see:

- Full ticket description
- Agent thoughts log
- Review notes (if any)
- Security scan results (if any)
- Test output

---

## 📊 Evals Dashboard

Access at `http://localhost:5050/evals-dashboard`

Shows:

- **Success Rate** — percentage of tickets that passed all gates
- **Done Count** — total merged tickets
- **Failed Count** — tickets that exhausted retries
- **Total Tickets** — all tickets processed
- **Recent Runs** — table of last 20 agent runs with status and time
- **Chart** — success rate over time (Chart.js line chart)

Data is read from `data/evals.jsonl` — a JSONL file with one entry per agent run.

---

## 🗂️ Project Structure

```
Shipyard/
├── src/
│   └── shipyard/
│       ├── __init__.py
│       ├── bot.py              # Telegram bot handlers
│       ├── server.py           # Flask server + Kanban board
│       ├── planner.py          # Planning model integration
│       ├── worktree_manager.py # Git worktree creation/isolation
│       ├── agent_runner.py     # Codex agent execution
│       ├── ticket_store.py     # Ticket state management
│       ├── evals.py            # Evals logging and dashboard
│       ├── demo_seed.py        # Demo project generator
│       ├── transcriber.py      # Whisper integration
│       ├── vision.py           # Vision model integration
│       └── templates/
│           ├── board.html      # Kanban board HTML
│           └── evals.html      # Evals dashboard HTML
├── data/                       # Runtime data (tickets.json, evals.jsonl)
├── .env.example                # Environment template
├── pyproject.toml              # Project metadata and dependencies
├── README.md                   # This file
└── LICENSE                     # MIT License
```

---

## 🔧 Built With

- **Codex** — All planning, coding, testing, reviewing agents
- **OpenAI Whisper** — Speech‑to‑text transcription
- **OpenAI GPT‑4o‑mini** — Vision description and planning
- **python‑telegram‑bot** — Telegram bot framework
- **Flask** — Web server for Kanban board and API
- **Git worktrees** — Isolated parallel execution environments
- **Chart.js** — Evals dashboard charts
- **Pytest** — Test suite for the project and agent verification

---

## 🛡️ Security

- `.env` is git‑ignored by default — never commit API keys.
- Never paste API keys into Telegram messages, screenshots, or commit messages.
- If a key is accidentally exposed, rotate it immediately at platform.openai.com or BotFather.
- All agent work happens in isolated worktrees under `/tmp/shipyard` — no cross‑ticket contamination.
- The Kanban board is served on `127.0.0.1` by default (localhost only). Bind to `0.0.0.0` only on trusted networks.

---

## 🗺️ Roadmap

- [x] Voice → parallel worktrees → test‑gated merge
- [x] Self‑healing retry loop (failure context fed back to agent)
- [x] Live Kanban board with agent thought streaming
- [x] Evals dashboard with Chart.js success rate tracking
- [x] Multimodal input (text + voice + photo/sketch)
- [x] Plan → Approve → Execute human‑in‑the‑loop flow
- [x] Reviewer agent with Accept/Ignore in Telegram
- [x] Security scanner agent (secrets, SQL injection patterns)
- [ ] Bootstrap brand‑new projects from a napkin sketch (no existing repo)
- [ ] Multi‑user team mode (shared board, role‑based approvals)
- [ ] Webhook mode for production deployment
- [ ] Slack integration

---

## ❓ FAQ

**Why Telegram instead of a web app?**
Telegram is already on every developer's phone. No installation, no accounts, no URLs to remember. Voice notes work perfectly. It's the fastest path from idea to execution.

**Is this just a wrapper around the Codex API?**
No. Shipyard introduces parallel sandboxing (git worktrees), a planning step with human approval, multi‑agent sequencing per ticket, live thought streaming, and a test‑gated merge flow. A raw API call gives you code; Shipyard gives you a verified, reviewed, merge‑ready branch.

**What happens if an agent gets stuck?**
Shipyard has a configurable retry limit (default: 3). Each retry includes the failure context. If all retries are exhausted, the ticket is marked Failed and the user is notified with the error details.

**Can I use this with my own repo?**
Yes. Point Shipyard at any local git repository, and it will create worktrees from that repo for each ticket.

**Does it work without Codex CLI?**
Shipyard has a fallback demo mode that uses standard OpenAI API calls when Codex CLI is unavailable. The full sandboxed agent experience requires Codex CLI.

---

## 🙋‍♂️ Built By

Solo developer — built entirely with Codex in under 7 hours during the Codex Hackathon, Pune 2026.

The tool that orchestrates the agents was written by the agent itself. That's maximum agentic leverage.

---

## 📄 License

MIT — see LICENSE for details.

---

**Shipyard — Speak, Ship, Done.**
