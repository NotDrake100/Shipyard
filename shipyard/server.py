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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@500;700;800;900&family=Patrick+Hand&display=swap');
    :root { color-scheme: light; font-family: "Inter", ui-sans-serif, system-ui, sans-serif; --hand: "Patrick Hand", "Comic Sans MS", "Bradley Hand", "Segoe Print", cursive; --ink: #0645a8; --line: #d8e4f2; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: #eef6fd; color: #17202a; display: block; overflow-y: auto; }
    .shell { position: relative; width: min(100vw - 18px, 1719px); min-height: calc(100vh - 24px); margin: 10px auto 32px; background: #fff; border: 1px solid #dce8f5; border-radius: 10px; box-shadow: 0 16px 38px rgba(26, 68, 111, .16); overflow: hidden; }
    .overlay-controls { position: absolute; z-index: 8; top: 26px; right: 24px; display: flex; align-items: center; gap: clamp(8px, 1.4vw, 20px); font-family: Inter, system-ui, sans-serif; pointer-events: auto; }
    .overlay-btn { height: 55px; min-width: 132px; border: 1.5px solid #c9dbef; border-radius: 8px; background: rgba(255,255,255,.92); color: var(--ink); display: inline-flex; align-items: center; justify-content: center; gap: 8px; font-size: 15px; font-weight: 900; box-shadow: 0 8px 18px rgba(22, 77, 143, .08); cursor: pointer; }
    .overlay-btn:hover { transform: translateY(-1px); box-shadow: 0 10px 22px rgba(22, 77, 143, .14); }
    .overlay-btn.primary { background: #075ed8; color: #fff; border-color: #075ed8; }
    header { min-height: 112px; display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 18px 190px 18px 32px; border-bottom: 2px solid #dce8f5; background: linear-gradient(180deg, #fff 0%, #fbfdff 100%); }
    .brand { display: flex; align-items: center; gap: 15px; color: var(--ink); }
    .brand-mark { width: 84px; height: 46px; position: relative; border-bottom: 3px solid var(--ink); }
    .brand-mark::before { content: ""; position: absolute; left: 12px; bottom: 3px; width: 42px; height: 30px; border: 3px solid var(--ink); border-bottom: 0; transform: skewY(-18deg); }
    .brand-mark::after { content: ""; position: absolute; right: 4px; bottom: 3px; width: 26px; height: 17px; border: 3px solid var(--ink); border-top: 0; border-radius: 0 0 12px 12px; }
    h1 { font-family: var(--hand); font-size: 44px; margin: 0; font-weight: 900; letter-spacing: 2px; color: var(--ink); text-transform: uppercase; }
    .tool { height: 42px; border: 1px solid #c6d6e7; border-radius: 7px; background: #fff; color: var(--ink); padding: 0 14px; font-weight: 700; }
    .primary { background: var(--ink); color: #fff; border-color: var(--ink); }
    a { color: var(--ink); text-decoration: none; font-family: Inter, system-ui, sans-serif; font-weight: 700; }
    main { position: relative; display: grid; grid-template-columns: repeat(6, minmax(0, 1fr)); pointer-events: none; width: 100%; margin: 0; padding: 0; min-height: calc(100vh - 148px); }
    .column { min-width: 0; padding: 24px 20px 34px; background: linear-gradient(180deg, #fff 0%, #fff 68%, #f9fcff 100%); border-left: 2px solid #dce8f5; }
    .column:first-child { border-left: 0; }
    .column h2 { min-height: 70px; display: flex; align-items: center; gap: 14px; margin: 0 0 12px; color: var(--ink); font-family: var(--hand); font-size: clamp(24px, 2vw, 38px); line-height: 1.05; font-weight: 900; letter-spacing: .5px; text-transform: uppercase; }
    .column h2::before { content: ""; width: 22px; height: 28px; border: 3px solid var(--ink); border-radius: 2px; box-shadow: inset 0 7px 0 rgba(6,69,168,.12); flex: 0 0 auto; }
    .underline { border-bottom: 2px solid var(--ink); padding-bottom: 3px; }
    .cards { display: flex; flex-direction: column; gap: clamp(12px, 1.4vw, 22px); align-items: stretch; pointer-events: auto; }
    .card { position: relative; min-height: clamp(92px, 8.9vw, 145px); border: 0; border-radius: 2px; background: #ffe99d; color: #17202a; padding: clamp(8px, .9vw, 14px); box-shadow: 0 12px 14px rgba(52, 65, 82, .20); transform: rotate(var(--tilt, -1deg)); transition: transform .65s cubic-bezier(.18,.78,.22,1), box-shadow .45s ease; cursor: pointer; will-change: transform; font-family: var(--hand); }
    .card::before { content: ""; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(255,255,255,.35), rgba(255,255,255,0) 28%); pointer-events: none; }
    .card:nth-child(2n) { --tilt: 1.2deg; background: #d7edff; }
    .card:nth-child(3n) { --tilt: -.7deg; background: #ffd3d6; }
    .card:nth-child(4n) { --tilt: .6deg; background: #e5f4a7; }
    .card:nth-child(5n) { --tilt: -1.4deg; background: #eadbf5; }
    .card:hover { transform: translateY(-11px) scale(1.025) rotate(.2deg); box-shadow: 0 22px 34px rgba(52, 65, 82, .26); }
    .card.fresh { animation: sticky-enter 1.1s cubic-bezier(.18,.78,.22,1) both; }
    .card.moved, .card.travelling { z-index: 4; animation: sticky-move 1.8s cubic-bezier(.18,.78,.22,1); }
    @keyframes sticky-enter {
      0% { opacity: 0; transform: translateY(18px) scale(.96) rotate(-5deg); }
      100% { opacity: 1; transform: translateY(0) scale(1) rotate(var(--tilt, -1deg)); }
    }
    @keyframes move-pop {
      0% { opacity: .3; transform: translateX(-28px) translateY(8px) scale(.94) rotate(-4deg); }
      55% { opacity: 1; transform: translateX(4px) translateY(-5px) scale(1.04) rotate(2deg); }
      100% { opacity: 1; transform: translateX(0) translateY(0) scale(1) rotate(var(--tilt, -1deg)); }
    }
    @keyframes sticky-move {
      0% { opacity: .35; transform: translateX(-34px) translateY(12px) rotate(-5deg) scale(.94); }
      55% { opacity: 1; transform: translateX(4px) translateY(-4px) rotate(2deg) scale(1.02); }
      78% { transform: translateX(-1px) translateY(1px) rotate(-1deg) scale(1); }
      100% { transform: translateX(0) translateY(0) rotate(var(--tilt, -1deg)) scale(1); }
    }
    .id { color: #314456; font-size: clamp(9px, .72vw, 12px); font-weight: 900; font-family: "Inter", system-ui, sans-serif; }
    .title { margin: 6px 0 8px; font-weight: 900; line-height: 1.05; font-size: clamp(16px, 1.18vw, 21px); border-bottom: 2px solid rgba(23,32,42,.55); padding-bottom: 4px; }
    .desc { color: #1f2933; font-family: "Inter", system-ui, sans-serif; font-size: clamp(10px, .78vw, 14px); line-height: 1.28; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
    .meta { margin-top: 8px; display: flex; align-items: center; justify-content: space-between; gap: 6px; font-size: clamp(9px, .7vw, 12px); font-family: Inter, system-ui, sans-serif; }
    .pill { background: rgba(15,74,162,.13); color: #173f84; border-radius: 5px; padding: 4px 7px; font-weight: 800; }
    .view { border: 1px solid rgba(15,74,162,.3); background: #fff; color: var(--ink); border-radius: 6px; padding: 4px 8px; font-weight: 900; cursor: pointer; }
    .check { color: #269153; font-size: clamp(20px, 1.7vw, 31px); font-family: Inter, system-ui, sans-serif; margin-left: auto; }
    .failed { background: #ffb2b8; }
    .empty { display: none; }
    dialog { width: min(980px, calc(100vw - 28px)); border: 0; border-radius: 10px; box-shadow: 0 24px 70px rgba(23,55,89,.28); padding: 0; overflow: hidden; }
    dialog::backdrop { background: rgba(17, 35, 58, .32); }
    .modal-head { display: flex; justify-content: space-between; align-items: center; padding: 16px 18px; border-bottom: 1px solid #d7e3ef; color: var(--ink); }
    .modal-head strong { font-size: 22px; }
    .close { border: 0; background: transparent; color: var(--ink); font-size: 25px; cursor: pointer; }
    .modal-body { padding: 18px; font-family: Inter, system-ui, sans-serif; line-height: 1.55; }
    .detail-grid { display: grid; grid-template-columns: .95fr 1.35fr; gap: 16px; align-items: stretch; }
    .simple-card { border: 1px solid #d4e4f5; border-radius: 8px; background: #f7fbff; padding: 14px; }
    .simple-card p { margin: 0 0 12px; }
    .node-map { position: relative; min-height: 360px; border: 1px solid #cfe0f1; border-radius: 8px; background: linear-gradient(180deg, #f9fcff, #eef6ff); overflow: hidden; }
    .node-map svg { position: absolute; inset: 0; width: 100%; height: 100%; }
    .node-line { fill: none; stroke: #0b60d1; stroke-width: 3.5; stroke-linecap: round; filter: drop-shadow(0 2px 2px rgba(8,78,170,.16)); stroke-dasharray: 540; stroke-dashoffset: 540; animation: draw-line .95s ease forwards; }
    .node-label { fill: #0750b8; font: 700 12px Inter, system-ui, sans-serif; }
    .node { position: absolute; width: 132px; min-height: 66px; border: 2px solid #0b60d1; border-radius: 8px; background: #fff; box-shadow: 0 12px 24px rgba(8, 67, 148, .16); padding: 10px; animation: node-pop .45s cubic-bezier(.2,.8,.2,1) both; }
    .node strong { display: block; color: #073b8f; font-size: 13px; line-height: 1.1; }
    .node span { display: block; color: #486581; font-size: 11px; margin-top: 5px; }
    .node.ticket { width: 168px; background: #fff6b8; border-color: #e2c34d; left: 4%; top: 11%; }
    .node.coder { left: 35%; top: 8%; animation-delay: .07s; }
    .node.tester { left: 67%; top: 10%; animation-delay: .14s; }
    .node.reviewer { left: 18%; top: 62%; animation-delay: .21s; }
    .node.security { left: 50%; top: 62%; animation-delay: .28s; }
    .node.done { left: 76%; top: 60%; background: #e8f6ff; animation-delay: .35s; }
    .port { position: absolute; width: 10px; height: 18px; background: #f39c12; border-radius: 2px; top: 50%; transform: translateY(-50%); }
    .port.in { left: -6px; }
    .port.out { right: -6px; }
    @keyframes draw-line { to { stroke-dashoffset: 0; } }
    @keyframes node-pop {
      0% { opacity: 0; transform: translateY(12px) scale(.94); }
      100% { opacity: 1; transform: translateY(0) scale(1); }
    }
    footer { display: none; }
    @media (max-width: 1100px) { .shell { width: 1200px; max-width: none; } body { overflow: auto; } .detail-grid { grid-template-columns: 1fr; } }
  </style>
</head>
<body>
  <div class="shell">
    <div class="overlay-controls" aria-label="Shipyard board controls">
      <a class="overlay-btn primary" href="/evals-dashboard">Evaluation</a>
    </div>
    <header>
      <div class="brand">
        <span class="brand-mark" aria-hidden="true"></span>
        <h1>Shipyard</h1>
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
    const statusOrder = {todo:0, in_progress:1, review:2, testing:3, ready_to_ship:4, done:5};
    let previous = JSON.parse(localStorage.getItem("shipyard-statuses") || "{}");
    let latestTickets = [];
    async function load() {
      const oldRects = new Map(Array.from(document.querySelectorAll(".card")).map(el => [el.dataset.key, el.getBoundingClientRect()]));
      const res = await fetch("/api/tickets");
      const data = await res.json();
      latestTickets = data.tickets;
      const byStatus = Object.fromEntries(columns.map(c => [c, []]));
      const next = {};
      for (const ticket of data.tickets) {
        const status = mapStatus(ticket.status || "todo");
        const key = `${ticket.request_id}:${ticket.id}`;
        ticket.moved = previous[key] && previous[key] !== status;
        ticket.fresh = !previous[key];
        next[key] = status;
        byStatus[status] ||= [];
        byStatus[status].push(ticket);
      }
      document.getElementById("board").innerHTML = columns.map(status => `
        <section class="column"><h2><span class="underline">${labels[status]}</span></h2>
          <div class="cards">${(byStatus[status] || []).map(card).join("")}</div>
        </section>`).join("");
      animateCardTransfers(oldRects);
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
      const key = `${esc(t.request_id)}:${esc(t.id)}`;
      return `<article class="card ${t.status === "failed" ? "failed" : ""} ${t.fresh ? "fresh" : ""} ${t.moved ? "moved" : ""}" data-key="${key}" onclick="openTicketGraph('${esc(t.request_id)}','${esc(t.id)}')">
        <div class="id">${esc(t.id)} · ${esc(labels[status])}</div>
        <div class="title">${esc(t.title)}</div>
        <div class="desc">${esc(t.description)}</div>
        <div class="meta">
          <span>▣ ${esc(t.due || "Today")}</span>
          <span class="pill">${esc(t.tag || labels[status])}</span>
          ${done ? `<button class="view" onclick="event.stopPropagation(); openTicketGraph('${esc(t.request_id)}','${esc(t.id)}')">View</button><span class="check">✓</span>` : ""}
        </div>
      </article>`;
    }
    function animateCardTransfers(oldRects) {
      for (const card of document.querySelectorAll(".card")) {
        const oldRect = oldRects.get(card.dataset.key);
        if (!oldRect) continue;
        const newRect = card.getBoundingClientRect();
        const dx = oldRect.left - newRect.left;
        const dy = oldRect.top - newRect.top;
        if (Math.abs(dx) < 2 && Math.abs(dy) < 2) continue;
        card.classList.add("travelling");
        card.style.transition = "none";
        card.style.transform = `translate(${dx}px, ${dy}px) rotate(var(--tilt, -1deg))`;
        requestAnimationFrame(() => {
          card.style.transition = "transform 1.8s cubic-bezier(.16,.84,.24,1), box-shadow .35s ease";
          card.style.transform = "translate(0, 0) rotate(var(--tilt, -1deg))";
          setTimeout(() => {
            card.classList.remove("travelling");
            card.style.transition = "";
            card.style.transform = "";
          }, 1850);
        });
      }
    }
    function openTicketGraph(requestId, ticketId) {
      const ticket = latestTickets.find(t => t.request_id === requestId && t.id === ticketId);
      if (!ticket) return;
      document.getElementById("detail-title").textContent = `${ticket.id}: ${ticket.title}`;
      const status = mapStatus(ticket.status || "todo");
      const order = statusOrder[status] ?? 0;
      const doneText = status === "done" ? "Done" : "Waiting";
      document.getElementById("detail-body").innerHTML = `
        <div class="detail-grid">
          <section class="simple-card">
            <p><strong>What this ticket does:</strong><br>${esc(ticket.description || "This task was completed.")}</p>
            <p><strong>Current stage:</strong> ${esc(labels[status] || status)}</p>
            <p><strong>Files touched:</strong><br>${esc((ticket.file_paths || []).join(", ") || "No files listed.")}</p>
            <p><strong>Agent notes in simple English:</strong><br>${esc(simpleEnglish(ticket.thoughts || "No notes yet."))}</p>
          </section>
          <section class="node-map" aria-label="Ticket agent node map">
            <svg viewBox="0 0 720 360" preserveAspectRatio="none" aria-hidden="true">
              <path class="node-line" style="animation-delay:.05s" d="M120 78 C190 78 205 60 256 60" />
              <path class="node-line" style="animation-delay:.16s" d="M390 60 C455 60 475 64 520 72" />
              <path class="node-line" style="animation-delay:.27s" d="M585 102 C610 145 580 190 520 230" />
              <path class="node-line" style="animation-delay:.38s" d="M470 250 C420 250 390 246 342 246" />
              <path class="node-line" style="animation-delay:.49s" d="M254 246 C190 246 175 220 135 125" />
              <text class="node-label" x="190" y="52">ticket</text>
              <text class="node-label" x="446" y="55">test</text>
              <text class="node-label" x="570" y="178">review</text>
              <text class="node-label" x="368" y="236">secure</text>
            </svg>
            <div class="node ticket"><span class="port out"></span><strong>${esc(ticket.id)}</strong><span>${esc(ticket.title)}</span></div>
            <div class="node coder"><span class="port in"></span><span class="port out"></span><strong>Coder</strong><span>${order >= 1 ? "Implemented" : "Queued"}</span></div>
            <div class="node tester"><span class="port in"></span><span class="port out"></span><strong>Tester</strong><span>${order >= 3 ? "Checked" : "Waiting"}</span></div>
            <div class="node reviewer"><span class="port in"></span><span class="port out"></span><strong>Reviewer</strong><span>${order >= 2 ? "Reviewed" : "Waiting"}</span></div>
            <div class="node security"><span class="port in"></span><span class="port out"></span><strong>Security</strong><span>No secrets found</span></div>
            <div class="node done"><span class="port in"></span><strong>${esc(doneText)}</strong><span>${status === "done" ? "Ready to ship" : "Moving through pipeline"}</span></div>
          </section>
        </div>
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
    :root { color-scheme: light; --bg:#edf6ff; --panel:#ffffff; --panel2:#f7fbff; --line:#cfe0f3; --text:#0c2140; --muted:#5d7390; --blue:#075ed8; --blue2:#4ea3ff; --red:#e84d5b; --gold:#f4b942; }
    * { box-sizing: border-box; }
    body { margin: 0; min-height: 100vh; background: radial-gradient(circle at 18% 0%, rgba(7,94,216,.12), transparent 26%), linear-gradient(180deg, #f8fcff 0%, var(--bg) 58%); color: var(--text); font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
    header { height: 76px; display: flex; align-items: center; justify-content: space-between; padding: 0 28px; border-bottom: 1px solid var(--line); background: rgba(255,255,255,.9); backdrop-filter: blur(16px); position: sticky; top: 0; z-index: 3; box-shadow: 0 10px 26px rgba(35, 85, 140, .08); }
    a { color: #fff; background: var(--blue); border-radius: 8px; padding: 12px 16px; text-decoration: none; font-weight: 900; box-shadow: 0 10px 18px rgba(7,94,216,.18); }
    .brand { display: flex; flex-direction: column; gap: 4px; }
    .brand strong { color: var(--blue); font-size: 22px; letter-spacing: .2px; }
    .brand span { color: var(--muted); font-size: 12px; }
    main { max-width: 1180px; margin: 0 auto; padding: 28px 22px 40px; }
    .hero { display: grid; grid-template-columns: 1.05fr .95fr; gap: 18px; align-items: stretch; }
    .panel { border: 1px solid var(--line); border-radius: 8px; background: linear-gradient(180deg, #ffffff, #f7fbff); box-shadow: 0 18px 44px rgba(30, 82, 135, .12); padding: 18px; }
    .score { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 18px; }
    .metric { border: 1px solid #cfe0f3; border-radius: 8px; background: #fff; padding: 14px; min-height: 98px; }
    .metric span { display:block; color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .08em; }
    .metric strong { display:block; margin-top: 8px; font-size: 34px; line-height: 1; }
    .metric small { display:block; color: var(--muted); margin-top: 8px; }
    .metric.good strong { color: var(--blue); }
    .metric.bad strong { color: var(--red); }
    .metric.gold strong { color: var(--gold); }
    h1, h2 { margin: 0; }
    h1 { color: #073b8f; font-size: clamp(30px, 4vw, 56px); line-height: .96; max-width: 720px; }
    .sub { color: #425b78; line-height: 1.55; max-width: 760px; margin: 14px 0 0; }
    .status-row { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 18px; }
    .badge { display: inline-flex; align-items: center; gap: 8px; border: 1px solid #c2d8f3; border-radius: 999px; padding: 8px 11px; color: #0750b8; background: #eef6ff; font-size: 13px; font-weight: 900; }
    .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--blue); box-shadow: 0 0 18px rgba(7,94,216,.42); }
    .charts { display: grid; grid-template-columns: .7fr 1.3fr; gap: 18px; margin-top: 18px; }
    .chart-wrap { min-height: 280px; }
    .chart-wrap h2, .table-panel h2 { font-size: 16px; margin-bottom: 14px; color: #073b8f; }
    table { width: 100%; border-collapse: collapse; font-size: 13px; }
    th, td { text-align: left; padding: 11px 8px; border-bottom: 1px solid #d9e7f6; color: #334e68; }
    th { color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .08em; }
    .state { display: inline-flex; align-items: center; border-radius: 999px; padding: 5px 9px; font-weight: 900; font-size: 12px; background: #e8f2ff; color: var(--blue); }
    .state.failed { background: #fff0f2; color: var(--red); }
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

      const palette = labels.map(label => label === "done" ? "#075ed8" : label === "failed" ? "#e84d5b" : "#4ea3ff");
      donutChart?.destroy();
      donutChart = new Chart(document.getElementById("donut"), {
        type: "doughnut",
        data: { labels, datasets: [{ data: values, backgroundColor: palette, borderWidth: 0 }] },
        options: { cutout: "70%", plugins: { legend: { position: "bottom", labels: { color: "#334e68", boxWidth: 12 } } } }
      });

      barChart?.destroy();
      barChart = new Chart(document.getElementById("bars"), {
        type: "bar",
        data: { labels, datasets: [{ label: "Latest Ticket State", data: values, backgroundColor: palette, borderRadius: 5 }] },
        options: {
          plugins: { legend: { labels: { color: "#173b66" } } },
          scales: {
            x: { grid: { color: "#e4eef9" }, ticks: { color: "#486581" } },
            y: { beginAtZero: true, grid: { color: "#e4eef9" }, ticks: { color: "#486581", precision: 0 } }
          }
        }
      });
      document.getElementById("runs").innerHTML = (data.recent || []).slice().reverse().map(run => {
        const status = run.status || "unknown";
        const rawNote = status === "done"
          ? "Coder, tester, reviewer, and security checks completed."
          : (run.error || "Needs attention.");
        const note = String(rawNote).replace(/[<>&]/g, m => ({'<':'&lt;','>':'&gt;','&':'&amp;'}[m]));
        return `<tr><td>${run.ticket_id || "-"}</td><td><span class="state ${status === "failed" ? "failed" : ""}">${status}</span></td><td>${run.pytest_returncode ?? "none"}</td><td>${note}</td></tr>`;
      }).join("") || `<tr><td colspan="4" class="empty">No evals logged yet.</td></tr>`;
    }
    load(); setInterval(load, 4000);
  </script>
</body>
</html>"""


if __name__ == "__main__":
    main()
