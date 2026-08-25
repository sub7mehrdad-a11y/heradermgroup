from datetime import datetime, timedelta

from .task_card import build_keyboard

REMINDER_INTERVAL = timedelta(hours=6)


def _parse(iso_text):
    return datetime.fromisoformat(iso_text)


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def check_and_send_reminders(state, tg, config, now):
    users = config["users"]
    dm_chats = state.get("dm_chats", {})

    for task in state["tasks"]:
        if task["status"] != "open":
            continue

        created_at = _parse(task["created_at"])
        last = task.get("last_reminder_at")
        base = _parse(last) if last else created_at
        if now - base < REMINDER_INTERVAL:
            continue

        # Reminders are private now — only the current assignee's DM, never
        # the group. If they never pressed /start there's no chat to send
        # to, so this task just goes unreminded until they do.
        dm_chat_id = dm_chats.get(task["assignee"])
        if not dm_chat_id:
            task["last_reminder_at"] = now.isoformat()
            continue

        raw_deadline = task.get("deadline")
        deadline = _parse(raw_deadline) if raw_deadline else None

        if deadline is None:
            prefix = "⏰ "
            deadline_line = "ددلاین: تعیین نشده"
        else:
            prefix = "⚠️ (از سررسید گذشته) " if now > deadline else "⏰ "
            deadline_line = f"ددلاین: {_fmt(deadline)}"

        text = (
            f"{prefix}یادآوری تسک #{task['id']}\n"
            f"{task['title']}\n"
            f"{deadline_line}"
        )

        try:
            # Same buttons as the task card, so the reminder itself is
            # actionable — no need to scroll up to find the original card.
            tg.send_message(dm_chat_id, text, reply_markup=build_keyboard(task, users))
        except Exception:
            pass  # e.g. user blocked the bot — don't fail the whole run over it

        task["last_reminder_at"] = now.isoformat()
