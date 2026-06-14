from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, Response

from shipyard.config import Settings, load_settings


def create_app(settings: Settings | None = None) -> Flask:
    settings = settings or load_settings()
    app = Flask(__name__)

    @app.get("/")
    def board() -> Response:
        return Response(_board_html(), mimetype="text/html")

    @app.get("/api/tickets")
    def api_tickets() -> Any:
        return jsonify({"tickets": collect_tickets(settings.inbox_dir)})

    @app.get("/evals-dashboard")
    def evals_dashboard() -> Response:
        return Response(_evals_html(), mimetype="text/html")

    @app.get("/api/evals")
    def api_evals() -> Any:
        return jsonify(evals_summary(settings.storage_dir / "evals.jsonl"))

    return app


def run_server(settings: Settings) -> None:
    app = create_app(settings)
    app.run(host=settings.server_host, port=settings.server_port, debug=False, use_reloader=False)


def main() -> None:
    run_server(load_settings())


def collect_tickets(inbox_dir: Path) -> list[dict[str, Any]]:
    tickets: list[dict[str, Any]] = []
    for tickets_path in inbox_dir.glob("*/*/tickets.json"):
        try:
            payload = json.loads(tickets_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, list):
            continue

        chat_id = tickets_path.parents[1].name
        request_id = tickets_path.parent.name
        for ticket in payload:
            worktree = ticket.get("worktree") or {}
            thoughts_path = Path(str(worktree.get("path", ""))) / "THOUGHTS.md"
            ticket = dict(ticket)
            ticket["chat_id"] = chat_id
            ticket["request_id"] = request_id
            ticket["thoughts"] = _tail(thoughts_path)
            tickets.append(ticket)
    return tickets


def evals_summary(evals_path: Path) -> dict[str, Any]:
    latest_by_ticket: dict[str, dict[str, Any]] = {}
    recent: list[dict[str, Any]] = []
    if evals_path.exists():
        for line in evals_path.read_text(encoding="utf-8").splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("event") == "agent_result":
                key = str(payload.get("worktree_path") or payload.get("ticket_id") or len(recent))
                latest_by_ticket[key] = payload
                recent.append(payload)
    latest = list(latest_by_ticket.values())
    counts: Counter[str] = Counter(str(item.get("status", "unknown")) for item in latest)
    total = sum(counts.values())
    done = counts.get("done", 0)
    failed = counts.get("failed", 0)
    success_rate = round((done / total) * 100) if total else 0
    return {
        "counts": dict(counts),
        "done": done,
        "failed": failed,
        "total": total,
        "success_rate": success_rate,
        "recent": recent[-12:],
        "latest": latest[-12:],
    }


def _tail(path: Path, max_chars: int = 1800) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    return text[-max_chars:]


def _board_html() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Shipyard Board</title>
  <style>
    :root { color-scheme: light; font-family: "Comic Sans MS", "Bradley Hand", "Segoe Print", ui-rounded, system-ui, sans-serif; --ink: #0645a8; --line: #d8e4f2; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: #eef6fd; color: #17202a; display: grid; place-items: start center; }
    .shell { position: relative; width: min(100vw - 18px, 1719px); aspect-ratio: 1719 / 915; margin: 10px auto; background: url("/static/shipyard-board-base.png") center / 100% 100% no-repeat; border-radius: 10px; box-shadow: 0 16px 38px rgba(26, 68, 111, .16); overflow: hidden; }
    .overlay-controls { position: absolute; z-index: 8; top: 4.05%; right: 2.55%; display: flex; align-items: center; gap: clamp(8px, 1.4vw, 20px); font-family: Inter, system-ui, sans-serif; pointer-events: auto; }
    .overlay-btn { height: clamp(40px, 4.15vw, 55px); min-width: clamp(92px, 8.8vw, 150px); border: 1.5px solid #c9dbef; border-radius: 8px; background: rgba(255,255,255,.92); color: var(--ink); display: inline-flex; align-items: center; justify-content: center; gap: 8px; font-size: clamp(13px, 1.05vw, 18px); font-weight: 800; box-shadow: 0 8px 18px rgba(22, 77, 143, .08); cursor: pointer; }
    .overlay-btn:hover { transform: translateY(-1px); box-shadow: 0 10px 22px rgba(22, 77, 143, .14); }
    .overlay-btn.primary { background: #075ed8; color: #fff; border-color: #075ed8; }
    header { display: none; }
    .brand { display: flex; align-items: center; gap: 15px; color: var(--ink); }
    .logo { width: 90px; height: 48px; }
    h1 { font-size: 34px; margin: 0; font-weight: 900; letter-spacing: 3px; color: var(--ink); text-transform: uppercase; }
    .tools { display: flex; align-items: center; gap: 10px; font-family: Inter, system-ui, sans-serif; }
    input { height: 42px; width: min(260px, 28vw); border: 1px solid #c6d6e7; border-radius: 7px; padding: 0 13px; color: #17304e; background: #fff; }
    .tool { height: 42px; border: 1px solid #c6d6e7; border-radius: 7px; background: #fff; color: var(--ink); padding: 0 14px; font-weight: 700; }
    .primary { background: var(--ink); color: #fff; border-color: var(--ink); }
    a { color: var(--ink); text-decoration: none; font-family: Inter, system-ui, sans-serif; font-weight: 700; }
    main { position: absolute; left: 1.55%; right: 1.55%; top: 29.5%; bottom: 5.5%; display: grid; grid-template-columns: repeat(6, 1fr); column-gap: 1.18%; pointer-events: none; }
    .column { min-width: 0; padding: 0 0.65%; background: transparent; border: 0; }
    .column h2 { display: none; }
    .icon { width: 42px; height: 42px; display: inline-flex; align-items: center; justify-content: center; color: var(--ink); }
    .icon svg { width: 42px; height: 42px; stroke: currentColor; fill: none; stroke-width: 2.3; stroke-linecap: round; stroke-linejoin: round; }
    .underline { border-bottom: 2px solid var(--ink); padding-bottom: 3px; }
    .cards { display: flex; flex-direction: column; gap: clamp(8px, 1.2vw, 15px); align-items: stretch; pointer-events: auto; }
    .card { position: relative; min-height: clamp(92px, 8.9vw, 145px); border: 0; border-radius: 2px; background: #ffe99d; color: #17202a; padding: clamp(8px, .9vw, 14px); box-shadow: 0 12px 14px rgba(52, 65, 82, .20); transform: rotate(var(--tilt, -1deg)); transition: transform .25s ease, box-shadow .25s ease; }
    .card::before { content: ""; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(255,255,255,.35), rgba(255,255,255,0) 28%); pointer-events: none; }
    .card:nth-child(2n) { --tilt: 1.2deg; background: #d7edff; }
    .card:nth-child(3n) { --tilt: -.7deg; background: #ffd3d6; }
    .card:nth-child(4n) { --tilt: .6deg; background: #e5f4a7; }
    .card:nth-child(5n) { --tilt: -1.4deg; background: #eadbf5; }
    .card:hover { transform: translateY(-4px) rotate(0deg); box-shadow: 0 18px 26px rgba(52, 65, 82, .25); }
    .card.moved { animation: sticky-move .85s cubic-bezier(.2,.8,.2,1); }
    @keyframes move-pop {
      0% { opacity: .3; transform: translateX(-28px) translateY(8px) scale(.94) rotate(-4deg); }
      55% { opacity: 1; transform: translateX(4px) translateY(-5px) scale(1.04) rotate(2deg); }
      100% { opacity: 1; transform: translateX(0) translateY(0) scale(1) rotate(var(--tilt, -1deg)); }
    }
    @keyframes sticky-move {
      0% { opacity: .25; transform: translateX(-38px) translateY(16px) rotate(-8deg) scale(.88); }
      45% { opacity: 1; transform: translateX(8px) translateY(-8px) rotate(5deg) scale(1.06); }
      72% { transform: translateX(-2px) translateY(2px) rotate(-2deg) scale(.99); }
      100% { transform: translateX(0) translateY(0) rotate(var(--tilt, -1deg)) scale(1); }
    }
    .id { color: #314456; font-size: clamp(9px, .72vw, 12px); font-weight: 900; font-family: Inter, system-ui, sans-serif; }
    .title { margin: 6px 0 8px; font-weight: 900; line-height: 1.16; font-size: clamp(12px, 1vw, 17px); border-bottom: 2px solid rgba(23,32,42,.55); padding-bottom: 4px; }
    .desc { color: #1f2933; font-size: clamp(10px, .78vw, 14px); line-height: 1.28; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .meta { margin-top: 8px; display: flex; align-items: center; justify-content: space-between; gap: 6px; font-size: clamp(9px, .7vw, 12px); font-family: Inter, system-ui, sans-serif; }
    .pill { background: rgba(15,74,162,.13); color: #173f84; border-radius: 5px; padding: 4px 7px; font-weight: 800; }
    .view { border: 1px solid rgba(15,74,162,.3); background: #fff; color: var(--ink); border-radius: 6px; padding: 4px 8px; font-weight: 900; cursor: pointer; }
    .check { color: #269153; font-size: clamp(20px, 1.7vw, 31px); font-family: Inter, system-ui, sans-serif; margin-left: auto; }
    .failed { background: #ffb2b8; }
    .empty { display: none; }
    dialog { width: min(560px, calc(100vw - 28px)); border: 0; border-radius: 10px; box-shadow: 0 24px 70px rgba(23,55,89,.28); padding: 0; }
    dialog::backdrop { background: rgba(17, 35, 58, .32); }
    .modal-head { display: flex; justify-content: space-between; align-items: center; padding: 16px 18px; border-bottom: 1px solid #d7e3ef; color: var(--ink); }
    .modal-head strong { font-size: 22px; }
    .close { border: 0; background: transparent; color: var(--ink); font-size: 25px; cursor: pointer; }
    .modal-body { padding: 18px; font-family: Inter, system-ui, sans-serif; line-height: 1.55; }
    footer { display: none; }
    @media (max-width: 900px) { .shell { width: 1200px; max-width: none; } body { overflow-x: auto; } }
  </style>
</head>
<body>
  <div class="shell">
    <div class="overlay-controls" aria-label="Shipyard board controls">
      <a class="overlay-btn primary" href="/evals-dashboard">Evaluation</a>
    </div>
    <header>
      <div class="brand">
        <svg class="logo" viewBox="0 0 120 62" aria-hidden="true">
          <path d="M8 51h104M16 49V17h42v32M18 18L42 5l18 13M28 49V29h20v20M58 49l18-22 21 22M74 28h20M84 20v29M92 49h15l5-10H99" fill="none" stroke="#0645a8" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>
          <path d="M73 16h16M80 10c8-5 12-2 15 2M70 42c8 3 19 3 29 0" fill="none" stroke="#0645a8" stroke-width="2" stroke-linecap="round"/>
        </svg>
        <h1>Shipyard</h1>
      </div>
      <div class="tools">
        <input id="search" placeholder="Search tasks..." aria-label="Search tasks">
        <button class="tool" type="button">⌁ Filter</button>
        <button class="tool primary" type="button">+ Add Task</button>
      </div>
    </header>
    <main id="board"></main>
    <footer>Sticky notes update every 2 seconds. Done notes have a View button.</footer>
  </div>
  <dialog id="detail">
    <div class="modal-head"><strong id="detail-title">Done</strong><button class="close" onclick="detail.close()">×</button></div>
    <div class="modal-body" id="detail-body"></div>
  </dialog>
  <script>
    const columns = ["todo", "in_progress", "review", "testing", "ready_to_ship", "done"];
    const labels = {todo:"To Do", in_progress:"In Progress", review:"Review", testing:"Testing", ready_to_ship:"Ready To Ship", done:"Done"};
    const icons = {
      todo:`<svg viewBox="0 0 48 48"><path d="M15 8h18v5h5v28H10V13h5z"/><path d="M17 20h14M17 27h14M17 34h10M17 8v6h14V8"/></svg>`,
      in_progress:`<svg viewBox="0 0 48 48"><path d="M7 39h34M14 38V13h19v25M15 14l11-7 8 7M20 38V22h9v16M31 38l7-11 5 11"/></svg>`,
      review:`<svg viewBox="0 0 48 48"><circle cx="21" cy="21" r="11"/><path d="M30 30l10 10"/></svg>`,
      testing:`<svg viewBox="0 0 48 48"><path d="M15 8h18v5h5v28H10V13h5z"/><path d="M17 20h14M17 27h14M17 34h10M17 8v6h14V8"/></svg>`,
      ready_to_ship:`<svg viewBox="0 0 48 48"><path d="M8 32h32l-5 8H15zM15 32V18h18v14M20 18v-6M27 18v-8M10 40c5 2 10 2 15 0 5 2 10 2 15 0"/></svg>`,
      done:`<svg viewBox="0 0 48 48"><path d="M12 13h25v25H12z"/><path d="M18 25l5 5 12-14"/></svg>`
    };
    let previous = JSON.parse(localStorage.getItem("shipyard-statuses") || "{}");
    let latestTickets = [];
    async function load() {
      const res = await fetch("/api/tickets");
      const data = await res.json();
      latestTickets = data.tickets;
      const term = document.getElementById("search").value.trim().toLowerCase();
      const byStatus = Object.fromEntries(columns.map(c => [c, []]));
      const next = {};
      for (const ticket of data.tickets.filter(t => !term || `${t.id} ${t.title} ${t.description}`.toLowerCase().includes(term))) {
        const status = mapStatus(ticket.status || "todo");
        const key = `${ticket.request_id}:${ticket.id}`;
        ticket.moved = previous[key] && previous[key] !== status;
        next[key] = status;
        byStatus[status] ||= [];
        byStatus[status].push(ticket);
      }
      document.getElementById("board").innerHTML = columns.map(status => `
        <section class="column"><h2><span class="icon">${icons[status]}</span><span class="underline">${labels[status]}</span></h2>
          <div class="cards">${(byStatus[status] || []).map(card).join("")}</div>
        </section>`).join("");
      previous = next;
      localStorage.setItem("shipyard-statuses", JSON.stringify(next));
    }
    function esc(value) { return String(value || "").replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[m])); }
    function mapStatus(status) {
      if (status === "failed") return "review";
      if (status === "review") return "review";
      if (status === "ready") return "ready_to_ship";
      if (status === "done") return "done";
      if (status === "testing") return "testing";
      if (status === "in_progress") return "in_progress";
      return "todo";
    }
    function card(t) {
      const status = mapStatus(t.status || "todo");
      const done = status === "done";
      return `<article class="card ${t.status === "failed" ? "failed" : ""} ${t.moved ? "moved" : ""}">
        <div class="id">${esc(t.id)} · ${esc(labels[status])}</div>
        <div class="title">${esc(t.title)}</div>
        <div class="desc">${esc(t.description)}</div>
        <div class="meta">
          <span>▣ ${esc(t.due || "Today")}</span>
          <span class="pill">${esc(t.tag || labels[status])}</span>
          ${done ? `<button class="view" onclick="openDone('${esc(t.request_id)}','${esc(t.id)}')">View</button><span class="check">✓</span>` : ""}
        </div>
      </article>`;
    }
    function openDone(requestId, ticketId) {
      const ticket = latestTickets.find(t => t.request_id === requestId && t.id === ticketId);
      if (!ticket) return;
      document.getElementById("detail-title").textContent = `${ticket.id}: ${ticket.title}`;
      document.getElementById("detail-body").innerHTML = `
        <p><strong>What was done:</strong> ${esc(ticket.description || "This task was completed.")}</p>
        <p><strong>Simple status:</strong> This sticky note is done and ready to check.</p>
        <p><strong>Files touched:</strong> ${esc((ticket.file_paths || []).join(", ") || "No files listed.")}</p>
        <p><strong>Agent notes:</strong></p>
        <p>${esc(simpleEnglish(ticket.thoughts || "No notes yet."))}</p>
      `;
      document.getElementById("detail").showModal();
    }
    function simpleEnglish(text) {
      return text.replace(/```[\\s\\S]*?```/g, "The agent ran its checks.")
        .replace(/[#*_`>{}\\[\\]]/g, "")
        .split("\\n")
        .map(line => line.trim())
        .filter(Boolean)
        .slice(-6)
        .join(" ");
    }
    document.getElementById("search").addEventListener("input", load);
    load(); setInterval(load, 2000);
  </script>
</body>
</html>"""


def _evals_html() -> str:
    return """<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Shipyard Evals</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <style>
    :root { color-scheme: dark; --bg:#070a0f; --panel:#101821; --panel2:#0c121a; --line:#203041; --text:#eef5ff; --muted:#93a4b7; --blue:#66b7ff; --green:#65d69a; --red:#ff6370; --gold:#ffd166; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: radial-gradient(circle at 18% 0%, rgba(42,117,204,.22), transparent 28%), linear-gradient(180deg, #0b1118 0%, var(--bg) 42%); color: var(--text); font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    header { height: 72px; display: flex; align-items: center; justify-content: space-between; padding: 0 26px; border-bottom: 1px solid var(--line); background: rgba(8, 13, 19, .82); backdrop-filter: blur(16px); position: sticky; top: 0; z-index: 3; }
    a { color: var(--blue); text-decoration: none; font-weight: 800; }
    .brand { display: flex; flex-direction: column; gap: 4px; }
    .brand strong { font-size: 20px; letter-spacing: .2px; }
    .brand span { color: var(--muted); font-size: 12px; }
    main { max-width: 1180px; margin: 0 auto; padding: 28px 22px 40px; }
    .hero { display: grid; grid-template-columns: 1.05fr .95fr; gap: 18px; align-items: stretch; }
    .panel { border: 1px solid var(--line); border-radius: 8px; background: linear-gradient(180deg, rgba(16,24,33,.96), rgba(10,16,23,.96)); box-shadow: 0 18px 44px rgba(0,0,0,.28); padding: 18px; }
    .score { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 18px; }
    .metric { border: 1px solid #1f3347; border-radius: 8px; background: rgba(9,16,24,.8); padding: 14px; min-height: 98px; }
    .metric span { display:block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .metric strong { display:block; margin-top: 8px; font-size: 34px; line-height: 1; }
    .metric small { display:block; color: var(--muted); margin-top: 8px; }
    .metric.good strong { color: var(--green); }
    .metric.bad strong { color: var(--red); }
    .metric.gold strong { color: var(--gold); }
    h1, h2 { margin: 0; }
    h1 { font-size: clamp(30px, 4vw, 56px); line-height: .96; max-width: 720px; }
    .sub { color: #b9c8d8; line-height: 1.55; max-width: 760px; margin: 14px 0 0; }
    .status-row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 18px; }
    .badge { display: inline-flex; align-items: center; gap: 8px; border: 1px solid #23425f; border-radius: 999px; padding: 8px 11px; color: #cfe6ff; background: rgba(18,35,53,.72); font-size: 13px; font-weight: 800; }
    .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--green); box-shadow: 0 0 18px rgba(101,214,154,.72); }
    .charts { display: grid; grid-template-columns: .7fr 1.3fr; gap: 18px; margin-top: 18px; }
    .chart-wrap { min-height: 280px; }
    .chart-wrap h2, .table-panel h2 { font-size: 16px; margin-bottom: 14px; color: #dceaff; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 11px 8px; border-bottom: 1px solid #1b2a39; color: #cad7e5; }
    th { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }
    .state { display: inline-flex; align-items: center; border-radius: 999px; padding: 5px 9px; font-weight: 900; font-size: 12px; background: rgba(101,214,154,.12); color: var(--green); }
    .state.failed { background: rgba(255,99,112,.12); color: var(--red); }
    .empty { color: var(--muted); padding: 24px 0; }
    @media (max-width: 900px) { .hero, .charts { grid-template-columns: 1fr; } .score { grid-template-columns: repeat(2, 1fr); } }
  </style>
</head>
<body>
  <header>
    <div class="brand"><strong>Shipyard Evals</strong><span>Agent performance and delivery health</span></div>
    <a href="/">Back to Board</a>
  </header>
  <main>
    <section class="hero">
      <div class="panel">
        <h1 id="headline">Shipyard is ready for demo.</h1>
        <p class="sub">This dashboard tracks the latest outcome for each agent ticket, so a successful retry replaces the earlier failed attempt instead of making stale failures look current.</p>
        <div class="status-row">
          <span class="badge"><span class="dot"></span> Telegram bot live</span>
          <span class="badge">Parallel ticket sandboxes</span>
          <span class="badge">Reviewer and security logs</span>
        </div>
      </div>
      <div class="panel">
        <div class="score">
          <div class="metric good"><span>Success Rate</span><strong id="success">0%</strong><small>latest ticket state</small></div>
          <div class="metric good"><span>Done</span><strong id="done">0</strong><small>ready to show</small></div>
          <div class="metric bad"><span>Failed</span><strong id="failed">0</strong><small>needs attention</small></div>
          <div class="metric gold"><span>Total</span><strong id="total">0</strong><small>tracked tickets</small></div>
        </div>
      </div>
    </section>
    <section class="charts">
      <div class="panel chart-wrap">
        <h2>Latest Outcome</h2>
        <canvas id="donut"></canvas>
      </div>
      <div class="panel chart-wrap">
        <h2>Agent Results</h2>
        <canvas id="bars"></canvas>
      </div>
    </section>
    <section class="panel table-panel" style="margin-top:18px">
      <h2>Recent Agent Runs</h2>
      <table>
        <thead><tr><th>Ticket</th><th>Status</th><th>Tester</th><th>Note</th></tr></thead>
        <tbody id="runs"></tbody>
      </table>
    </section>
  </main>
  <script>
    let donutChart;
    let barChart;
    async function load() {
      const res = await fetch("/api/evals");
      const data = await res.json();
      const labels = ["done", "failed", "unknown"].filter(key => data.counts[key]);
      const values = labels.map(k => data.counts[k]);
      document.getElementById("success").textContent = `${data.success_rate || 0}%`;
      document.getElementById("done").textContent = data.done || 0;
      document.getElementById("failed").textContent = data.failed || 0;
      document.getElementById("total").textContent = data.total || 0;
      document.getElementById("headline").textContent = (data.failed || 0) === 0 && (data.total || 0) > 0
        ? "All current tickets are passing."
        : "Shipyard is tracking agent health.";

      const palette = labels.map(label => label === "done" ? "#65d69a" : label === "failed" ? "#ff6370" : "#66b7ff");
      donutChart?.destroy();
      donutChart = new Chart(document.getElementById("donut"), {
        type: "doughnut",
        data: { labels, datasets: [{ data: values, backgroundColor: palette, borderWidth: 0 }] },
        options: { cutout: "70%", plugins: { legend: { position: "bottom", labels: { color: "#cfe0ef", boxWidth: 12 } } } }
      });

      barChart?.destroy();
      barChart = new Chart(document.getElementById("bars"), {
        type: "bar",
        data: { labels, datasets: [{ label: "Latest Ticket State", data: values, backgroundColor: palette, borderRadius: 5 }] },
        options: {
          plugins: { legend: { labels: { color: "#e8edf2" } } },
          scales: {
            x: { grid: { color: "#142230" }, ticks: { color: "#b7c5d0" } },
            y: { beginAtZero: true, grid: { color: "#142230" }, ticks: { color: "#b7c5d0", precision: 0 } }
          }
        }
      });
      document.getElementById("runs").innerHTML = (data.recent || []).slice().reverse().map(run => {
        const status = run.status || "unknown";
        const note = String(run.error || "Completed").replace(/[<>&]/g, m => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[m]));
        return `<tr><td>${run.ticket_id || "-"}</td><td><span class="state ${status === "failed" ? "failed" : ""}">${status}</span></td><td>${run.pytest_returncode ?? "none"}</td><td>${note}</td></tr>`;
      }).join("") || `<tr><td colspan="4" class="empty">No evals logged yet.</td></tr>`;
    }
    load(); setInterval(load, 4000);
  </script>
</body>
</html>"""


if __name__ == "__main__":
    main()
