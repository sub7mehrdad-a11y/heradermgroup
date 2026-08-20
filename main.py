import os
import sys

from src.telegram_api import TelegramAPI
from src.storage import load_state, save_state, load_config
from src.commands import process_update, mark_done, handoff_task
from src.ai_flow import handle_free_text
from src.reminders import check_and_send_reminders
from src.date_parser import now_iran
from src.task_card import format_task_card, build_keyboard

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE, "data", "tasks.json")
CONFIG_PATH = os.path.join(BASE, "data", "config.json")


def _find_task(state, task_id):
    return next((t for t in state["tasks"] if t["id"] == task_id), None)


def _refresh_card(tg, state, config, task_id):
    task = _find_task(state, task_id)
    if task is None or not task.get("task_message_id"):
        return
    try:
        tg.edit_message_text(
            task["chat_id"], task["task_message_id"],
            format_task_card(task, config["users"]),
            reply_markup=build_keyboard(task, config["users"]),
        )
    except Exception as e:
        print("edit failed:", e)


def _send_items(tg, state, config, chat_id, thread_id, items):
    for item in items:
        if "edit_task_id" in item:
            _refresh_card(tg, state, config, item["edit_task_id"])
            continue
        result = tg.send_message(
            chat_id, item["text"],
            message_thread_id=thread_id,
            reply_markup=item.get("reply_markup"),
        )
        if item.get("attach_task_id") and result:
            task = _find_task(state, item["attach_task_id"])
            if task:
                task["task_message_id"] = result.get("message_id")


def _handle_callback(state, config, tg, cq):
    data = cq.get("data", "")
    from_user = cq.get("from", {}) or {}
    username = (from_user.get("username") or "").lower()
    users = config["users"]

    if username not in users or ":" not in data:
        tg.answer_callback_query(cq["id"])
        return

    action, _, id_text = data.partition(":")
    try:
        task_id = int(id_text)
    except ValueError:
        tg.answer_callback_query(cq["id"])
        return

    if action == "done":
        ok, msg, _task = mark_done(state, task_id, username, "")
    elif action == "handoff":
        ok, msg, _task = handoff_task(state, config, task_id, username, "")
    else:
        ok, msg = False, None

    tg.answer_callback_query(cq["id"], text=(msg[:190] if msg else None))
    if ok:
        _refresh_card(tg, state, config, task_id)


def _handle_private(state, tg, msg):
    from_user = msg.get("from", {}) or {}
    username = (from_user.get("username") or "").lower()

    state.setdefault("dm_chats", {})
    state["dm_chats"][username] = msg["chat"]["id"]
    if (msg.get("text") or "").strip() == "/start":
        tg.send_message(
            msg["chat"]["id"],
            "ثبت شد ✅ از این به بعد یادآوری‌های خصوصی تسک‌هات رو همینجا هم برات می‌فرستم.",
        )


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN تنظیم نشده.")
        sys.exit(1)
    gemini_key = os.environ.get("GEMINI_API_KEY")

    tg = TelegramAPI(token)
    state = load_state(STATE_PATH)
    config = load_config(CONFIG_PATH)

    offset = state.get("offset", 0) or None
    while True:
        updates = tg.get_updates(offset=offset)
        if not updates:
            break
        for u in updates:
            offset = u["update_id"] + 1

            cq = u.get("callback_query")
            if cq:
                _handle_callback(state, config, tg, cq)
                continue

            msg = u.get("message")
            if not msg:
                continue

            # Only usernames registered in known usernames may register a
            # DM; unknown senders in a private chat are ignored entirely.
            if msg.get("chat", {}).get("type") == "private":
                from_user = msg.get("from", {}) or {}
                if (from_user.get("username") or "").lower() in config["users"]:
                    _handle_private(state, tg, msg)
                continue

            text = (msg.get("text") or "").strip()
            chat_id = msg["chat"]["id"]
            thread_id = msg.get("message_thread_id")

            if text.startswith("/"):
                items = process_update(state, config, msg)
            else:
                items = handle_free_text(state, config, msg, gemini_key)

            _send_items(tg, state, config, chat_id, thread_id, items)

        if len(updates) < 100:
            break
    state["offset"] = offset or 0

    check_and_send_reminders(state, tg, config, now_iran())

    save_state(STATE_PATH, state)


if __name__ == "__main__":
    main()
