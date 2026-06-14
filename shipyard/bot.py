from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Message, Update
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)
from telegram.request import HTTPXRequest

from shipyard.agents import AgentRunner
from shipyard.ai import AIService
from shipyard.config import Settings, load_settings
from shipyard.media import build_request_id, ensure_request_dir, utc_now
from shipyard.planning import PlanStore, PlanningService, ProjectPlan, Ticket
from shipyard.server import run_server
from shipyard.state import PendingPhoto, PendingPhotoStore
from shipyard.worktrees import WorktreeManager, enrich_tickets_with_worktrees

logger = logging.getLogger(__name__)
TELEGRAM_MESSAGE_LIMIT = 3900


@dataclass(frozen=True)
class IntakeServices:
    settings: Settings
    ai: AIService
    planner: PlanningService
    plans: PlanStore
    worktrees: WorktreeManager
    agents: AgentRunner
    pending_photos: PendingPhotoStore


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message:
        return

    await message.reply_text(
        "Shipyard is ready. Send a voice note describing what you want to build. "
        "If you have a sketch, send the photo first or reply to it with your voice note."
    )


async def evals(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    services = _services(context)
    if not message:
        return

    evals_path = services.settings.storage_dir / "evals.jsonl"
    if not evals_path.exists():
        await message.reply_text("No evals logged yet.")
        return

    total = 0
    done = 0
    failed = 0
    for line in evals_path.read_text(encoding="utf-8").splitlines()[-100:]:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if payload.get("event") == "agent_result":
            total += 1
            done += payload.get("status") == "done"
            failed += payload.get("status") == "failed"

    await message.reply_text(
        f"Evals summary\n\nRecent agent runs: {total}\nDone: {done}\nFailed: {failed}"
    )


async def board(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    services = _services(context)
    if not message:
        return

    url = f"http://{services.settings.server_host}:{services.settings.server_port}"
    await message.reply_text(f"Kanban board: {url}\nEvals dashboard: {url}/evals-dashboard")


async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    services = _services(context)
    if not message or not chat or not message.photo:
        return

    try:
        request_id = build_request_id(message.message_id)
        request_dir = ensure_request_dir(services.settings.inbox_dir, chat.id, request_id)
        photo_path = request_dir / "sketch.jpg"
        await _download_telegram_file(context, message.photo[-1].file_id, photo_path)

        services.pending_photos.remember(
            PendingPhoto(
                chat_id=chat.id,
                message_id=message.message_id,
                file_path=photo_path,
                created_at=utc_now(),
            )
        )

        payload = {
            "request_id": request_id,
            "chat_id": chat.id,
            "photo_message_id": message.message_id,
            "created_at": utc_now().isoformat(),
            "audio_path": None,
            "sketch_path": str(photo_path),
            "transcript": (message.caption or "").strip(),
            "sketch_description": None,
        }
        _write_request_payload(request_dir / "request.json", payload)

        if message.caption:
            status_message = await message.reply_text("Sketch saved. Describing it now.")
            await _describe_sketch_and_send_plan(
                services,
                chat.id,
                request_id,
                photo_path,
                status_message,
            )
            return

        await message.reply_text(
            "Sketch saved. Send text or a voice note to add context, or plan from this sketch.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("Plan from this sketch", callback_data=f"plan_sketch:{request_id}")]]
            ),
        )
    except Exception:
        logger.exception("Failed to save Telegram photo")
        await message.reply_text("I could not save that sketch. Please try sending it again.")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    services = _services(context)
    if not message or not chat:
        return

    voice_file_id = _audio_file_id(message)
    if not voice_file_id:
        await message.reply_text("Please send a Telegram voice note or audio file.")
        return

    request_id = build_request_id(message.message_id)
    request_dir = ensure_request_dir(services.settings.inbox_dir, chat.id, request_id)
    audio_path = request_dir / _audio_filename(message)
    sketch_path = request_dir / "sketch.jpg"

    status_message = await message.reply_text("Got it. Transcribing the voice note now.")

    try:
        await _download_telegram_file(context, voice_file_id, audio_path)
        attached_sketch_path = await _resolve_sketch(update, context, services, sketch_path)

        transcript, sketch_description = await _process_media(
            services.ai,
            audio_path,
            attached_sketch_path,
        )

        payload = {
            "request_id": request_id,
            "chat_id": chat.id,
            "voice_message_id": message.message_id,
            "created_at": utc_now().isoformat(),
            "audio_path": str(audio_path),
            "sketch_path": str(attached_sketch_path) if attached_sketch_path else None,
            "transcript": transcript,
            "sketch_description": sketch_description,
        }
        _write_request_payload(request_dir / "request.json", payload)

        if attached_sketch_path:
            services.pending_photos.clear(chat.id)

        await _send_plan_for_payload(services, chat.id, payload, status_message)
    except Exception:
        logger.exception("Failed to process Telegram voice intake")
        await status_message.edit_text(
            "I could not finish that request, but any downloaded media was kept in data/inbox. "
            "Try again with a shorter text request if you need to move fast."
        )


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    chat = update.effective_chat
    services = _services(context)
    if not message or not chat or not message.text:
        return

    if _is_greeting(message.text):
        await message.reply_text(
            "Shipyard is listening. Send a project idea as text, voice, photo, or any combination."
        )
        return

    request_id = build_request_id(message.message_id)
    request_dir = ensure_request_dir(services.settings.inbox_dir, chat.id, request_id)
    sketch_path = request_dir / "sketch.jpg"
    status_message = await message.reply_text("Got it. Reading your text request now.")

    try:
        attached_sketch_path = await _resolve_sketch(update, context, services, sketch_path)
        sketch_description = (
            await services.ai.describe_sketch(attached_sketch_path)
            if attached_sketch_path
            else None
        )

        payload = {
            "request_id": request_id,
            "chat_id": chat.id,
            "text_message_id": message.message_id,
            "created_at": utc_now().isoformat(),
            "audio_path": None,
            "sketch_path": str(attached_sketch_path) if attached_sketch_path else None,
            "transcript": message.text.strip(),
            "sketch_description": sketch_description,
        }
        _write_request_payload(request_dir / "request.json", payload)

        if attached_sketch_path:
            services.pending_photos.clear(chat.id)

        await _send_plan_for_payload(services, chat.id, payload, status_message)
    except Exception:
        logger.exception("Failed to process Telegram text intake")
        await status_message.edit_text(
            "I could not finish that text request. Try sending it again in one shorter message."
        )


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message:
        return

    await query.answer()
    services = _services(context)
    chat_id = query.message.chat_id
    data = query.data or ""

    try:
        if data.startswith("plan_sketch:"):
            request_id = data.removeprefix("plan_sketch:")
            payload = services.plans.request_payload(chat_id, request_id)
            sketch_path = payload.get("sketch_path")
            if not sketch_path:
                await query.edit_message_text("I could not find the saved sketch for that request.")
                return

            await query.edit_message_text("Describing the sketch and drafting a plan now.")
            await _describe_sketch_and_send_plan(
                services,
                chat_id,
                request_id,
                Path(str(sketch_path)),
                query.message,
            )
            return

        if data.startswith("approve_plan:"):
            request_id = data.removeprefix("approve_plan:")
            plan = services.plans.approve_plan(chat_id, request_id)
            await query.edit_message_text("Approved. Creating isolated worktrees now.")
            records = services.worktrees.create_for_plan(chat_id, plan)
            enrich_tickets_with_worktrees(
                services.plans.tickets_path(chat_id, request_id),
                records,
            )
            await query.edit_message_text(
                _format_approved_plan(plan, records_created=len(records))
                + "\n\nAgents are starting now.",
                reply_markup=_approved_markup(plan),
            )
            asyncio.create_task(_run_agents_and_notify(context, chat_id, request_id))
            return

        if data.startswith("run_agents:"):
            request_id = data.removeprefix("run_agents:")
            plan = services.plans.get_plan(chat_id, request_id)
            await query.edit_message_text(
                f"Agents started for {plan.project_name}. I will message when they finish."
            )
            asyncio.create_task(_run_agents_and_notify(context, chat_id, request_id))
            return

        if data.startswith("retry_ticket:"):
            _, request_id, ticket_id = data.split(":", 2)
            await query.edit_message_text(f"Retrying {ticket_id}. I will message when it finishes.")
            asyncio.create_task(_retry_ticket_and_notify(context, chat_id, request_id, ticket_id))
            return

        if data.startswith("merge_ticket:"):
            _, request_id, ticket_id = data.split(":", 2)
            await query.edit_message_text(_merge_ticket(services, chat_id, request_id, ticket_id))
            return

        if data.startswith("ticket:"):
            _, request_id, ticket_id = data.split(":", 2)
            plan = services.plans.get_plan(chat_id, request_id)
            ticket = next((item for item in plan.tickets if item.id == ticket_id), None)
            if ticket is None:
                await query.message.reply_text("I could not find that ticket.")
                return
            await query.message.reply_text(
                _format_ticket_detail(ticket),
                reply_markup=_ticket_action_markup(request_id, ticket_id),
            )
            return
    except Exception:
        logger.exception("Failed to handle Telegram callback")
        await query.message.reply_text("I could not complete that action. Please check the logs.")


async def _run_agents_and_notify(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    request_id: str,
) -> None:
    services = context.application.bot_data["services"]
    tickets_path = services.plans.tickets_path(chat_id, request_id)
    try:
        results = await asyncio.to_thread(services.agents.run_for_tickets_file, tickets_path)
        done = sum(1 for result in results if result.status == "done")
        failed = sum(1 for result in results if result.status == "failed")
        await context.bot.send_message(
            chat_id=chat_id,
            text=(
                "Agent run finished.\n\n"
                f"Done: {done}\n"
                f"Failed: {failed}\n"
                f"Tickets file: {tickets_path}"
            ),
            reply_markup=_post_agent_markup(chat_id, request_id, context),
        )
    except Exception:
        logger.exception("Agent run failed")
        await context.bot.send_message(
            chat_id=chat_id,
            text="Agent run failed before completion. Check the bot logs and tickets.json.",
        )


async def _retry_ticket_and_notify(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    request_id: str,
    ticket_id: str,
) -> None:
    services = context.application.bot_data["services"]
    tickets_path = services.plans.tickets_path(chat_id, request_id)
    tickets = services.plans.tickets_payload(chat_id, request_id)
    retry_tickets = [ticket for ticket in tickets if str(ticket.get("id")) == ticket_id]
    results = await asyncio.to_thread(
        services.agents.run_ticket_payloads,
        tickets_path,
        retry_tickets,
    )
    status = results[0].status if results else "not-found"
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Retry finished for {ticket_id}: {status}",
        reply_markup=_ticket_action_markup(request_id, ticket_id),
    )


def _merge_ticket(
    services: IntakeServices,
    chat_id: int,
    request_id: str,
    ticket_id: str,
) -> str:
    tickets = services.plans.tickets_payload(chat_id, request_id)
    ticket = next((item for item in tickets if str(item.get("id")) == ticket_id), None)
    if not ticket or not ticket.get("worktree"):
        return f"No worktree found for {ticket_id}."

    branch = str(ticket["worktree"]["branch"])
    result = subprocess.run(
        ["git", "merge", "--no-ff", "--no-edit", branch],
        cwd=Path.cwd(),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return "Merge failed:\n" + _truncate_for_telegram(result.stdout + result.stderr)

    ticket["status"] = "done"
    ticket["merged_at"] = utc_now().isoformat()
    services.plans.save_tickets_payload(chat_id, request_id, tickets)
    return f"Merged {ticket_id} from {branch} into the current branch."


async def _describe_sketch_and_send_plan(
    services: IntakeServices,
    chat_id: int,
    request_id: str,
    sketch_path: Path,
    status_message: Message,
) -> None:
    payload = services.plans.request_payload(chat_id, request_id)
    payload["sketch_description"] = await services.ai.describe_sketch(sketch_path)
    services.plans.save_request_payload(chat_id, request_id, payload)
    await _send_plan_for_payload(services, chat_id, payload, status_message)


async def _send_plan_for_payload(
    services: IntakeServices,
    chat_id: int,
    payload: dict[str, object],
    status_message: Message,
) -> None:
    await status_message.edit_text("Intake saved. Drafting the project plan now.")
    plan = await services.planner.generate_plan(payload)
    services.plans.save_plan(chat_id, plan)
    await status_message.edit_text(
        _format_plan(plan),
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("Approve & Start", callback_data=f"approve_plan:{plan.request_id}")]]
        ),
    )


async def _process_media(
    ai: AIService,
    audio_path: Path,
    sketch_path: Path | None,
) -> tuple[str, str | None]:
    transcript_task = asyncio.create_task(ai.transcribe_audio(audio_path))
    sketch_task = (
        asyncio.create_task(ai.describe_sketch(sketch_path))
        if sketch_path is not None
        else None
    )

    transcript = await transcript_task
    sketch_description = await sketch_task if sketch_task else None
    return transcript, sketch_description


async def _resolve_sketch(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    services: IntakeServices,
    target_path: Path,
) -> Path | None:
    message = update.effective_message
    chat = update.effective_chat
    if not message or not chat:
        return None

    reply_photo = _reply_photo_file_id(message)
    if reply_photo:
        await _download_telegram_file(context, reply_photo, target_path)
        return target_path

    pending_photo = services.pending_photos.get_recent(
        chat.id,
        services.settings.pending_photo_ttl_minutes,
    )
    if pending_photo is None:
        return None

    target_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pending_photo.file_path, target_path)
    return target_path


def _audio_file_id(message: Message) -> str | None:
    if message.voice:
        return message.voice.file_id
    if message.audio:
        return message.audio.file_id
    return None


def _audio_filename(message: Message) -> str:
    if message.voice:
        return "voice.oga"
    if message.audio and message.audio.file_name:
        suffix = Path(message.audio.file_name).suffix or ".mp3"
        return f"audio{suffix}"
    return "audio.mp3"


def _reply_photo_file_id(message: Message) -> str | None:
    reply = message.reply_to_message
    if not reply or not reply.photo:
        return None
    return reply.photo[-1].file_id


async def _download_telegram_file(
    context: ContextTypes.DEFAULT_TYPE,
    file_id: str,
    destination: Path,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    telegram_file = await context.bot.get_file(file_id)
    await telegram_file.download_to_drive(custom_path=destination)


def _write_request_payload(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)


def _format_intake_response(transcript: str, sketch_description: str | None) -> str:
    sections = ["Voice transcript:", transcript or "(No transcript returned.)"]
    if sketch_description:
        sections.extend(["", "Sketch description:", sketch_description])
    else:
        sections.extend(["", "No sketch was attached."])

    sections.extend(["", "Next step: planning and ticket splitting will use this payload."])
    return _truncate_for_telegram("\n".join(sections))


def _format_plan(plan: ProjectPlan) -> str:
    ticket_lines = [
        f"{ticket.id}. {ticket.title}"
        for ticket in plan.tickets
    ]
    sections = [
        f"Project plan: {plan.project_name}",
        "",
        plan.summary,
        "",
        "Tech stack:",
        *[f"- {item}" for item in plan.tech_stack],
        "",
        "Tickets:",
        *ticket_lines,
        "",
        "Approve to create these tickets.",
    ]
    return _truncate_for_telegram("\n".join(section for section in sections if section is not None))


def _format_approved_plan(plan: ProjectPlan, records_created: int = 0) -> str:
    return _truncate_for_telegram(
        "\n".join(
            [
                f"Approved: {plan.project_name}",
                "",
                f"{len(plan.tickets)} tickets created in To Do.",
                f"{records_created} isolated worktrees created under /tmp/shipyard.",
                "Select a ticket below to inspect it.",
            ]
        )
    )


def _ticket_selection_markup(plan: ProjectPlan) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(f"{ticket.id}: {ticket.title[:35]}", callback_data=f"ticket:{plan.request_id}:{ticket.id}")]
        for ticket in plan.tickets
    ]
    return InlineKeyboardMarkup(rows)


def _approved_markup(plan: ProjectPlan) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton("Run Agents", callback_data=f"run_agents:{plan.request_id}")]]
    rows.extend(_ticket_selection_markup(plan).inline_keyboard)
    return InlineKeyboardMarkup(rows)


def _post_agent_markup(
    chat_id: int,
    request_id: str,
    context: ContextTypes.DEFAULT_TYPE,
) -> InlineKeyboardMarkup | None:
    services = context.application.bot_data["services"]
    tickets = services.plans.tickets_payload(chat_id, request_id)
    rows = []
    for ticket in tickets:
        ticket_id = str(ticket.get("id"))
        status = str(ticket.get("status"))
        if status == "done":
            rows.append(
                [InlineKeyboardButton(f"Merge {ticket_id}", callback_data=f"merge_ticket:{request_id}:{ticket_id}")]
            )
        if status == "failed":
            rows.append(
                [InlineKeyboardButton(f"Retry {ticket_id}", callback_data=f"retry_ticket:{request_id}:{ticket_id}")]
            )
    return InlineKeyboardMarkup(rows) if rows else None


def _ticket_action_markup(request_id: str, ticket_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Retry", callback_data=f"retry_ticket:{request_id}:{ticket_id}")],
            [InlineKeyboardButton("Merge", callback_data=f"merge_ticket:{request_id}:{ticket_id}")],
        ]
    )


def _format_ticket_detail(ticket: Ticket) -> str:
    return _truncate_for_telegram(
        "\n".join(
            [
                f"{ticket.id}: {ticket.title}",
                "",
                ticket.description,
                "",
                "Files:",
                *[f"- {path}" for path in ticket.file_paths],
                "",
                "Dependencies:",
                ", ".join(ticket.dependencies) if ticket.dependencies else "None",
                "",
                f"Status: {ticket.status}",
            ]
        )
    )


def _truncate_for_telegram(text: str) -> str:
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        return text

    suffix = "\n\n[Output truncated. Full intake is saved in request.json.]"
    return text[: TELEGRAM_MESSAGE_LIMIT - len(suffix)].rstrip() + suffix


def _is_greeting(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {"hi", "hello", "hey", "/hi"}


def _services(context: ContextTypes.DEFAULT_TYPE) -> IntakeServices:
    services = context.application.bot_data.get("services")
    if not isinstance(services, IntakeServices):
        raise RuntimeError("Shipyard services were not initialized")
    return services


def build_application(settings: Settings | None = None) -> Application:
    settings = settings or load_settings()
    services = IntakeServices(
        settings=settings,
        ai=AIService(settings),
        planner=PlanningService(settings),
        plans=PlanStore(settings.inbox_dir),
        worktrees=WorktreeManager(Path.cwd(), settings.worktree_root),
        agents=AgentRunner(settings.storage_dir / "evals.jsonl", max_workers=4, codex_timeout_seconds=4),
        pending_photos=PendingPhotoStore(settings.state_dir),
    )

    timeout = settings.telegram_network_timeout_seconds
    request = HTTPXRequest(
        connect_timeout=timeout,
        read_timeout=timeout,
        write_timeout=timeout,
        pool_timeout=timeout,
    )
    application = (
        ApplicationBuilder()
        .token(settings.telegram_bot_token)
        .request(request)
        .get_updates_request(request)
        .build()
    )
    application.bot_data["services"] = services
    application.add_handler(CallbackQueryHandler(handle_callback))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("evals", evals))
    application.add_handler(CommandHandler("board", board))
    application.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    application.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    return application


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    settings = load_settings()
    if settings.enable_server:
        threading.Thread(target=run_server, args=(settings,), daemon=True).start()
    application = build_application(settings)
    application.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=5)


if __name__ == "__main__":
    main()
