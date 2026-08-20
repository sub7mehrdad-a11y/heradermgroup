from datetime import datetime, timedelta

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

        deadline = _parse(task["deadline"])
        assignee_name = users.get(task["assignee"], task["assignee"])
        overdue = now > deadline
        prefix = "⚠️ (از سررسید گذشته) " if overdue else "⏰ "
        text = (
            f"{prefix}یادآوری تسک #{task['id']} برای {assignee_name}\n"
            f"{task['title']}\n"
            f"ددلاین: {_fmt(deadline)}"
        )

        tg.send_message(task["chat_id"], text, message_thread_id=task.get("thread_id"))

        dm_chat_id = dm_chats.get(task["assignee"])
        if dm_chat_id:
            try:
                tg.send_message(dm_chat_id, text)
            except Exception:
                pass  # e.g. user blocked the bot — don't fail the whole run over it

        task["last_reminder_at"] = now.isoformat()
