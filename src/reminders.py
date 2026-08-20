from datetime import datetime, timedelta

BEFORE_THRESHOLDS = [
    ("before_24h", timedelta(hours=24)),
    ("before_2h", timedelta(hours=2)),
]
OVERDUE_INTERVAL = timedelta(hours=6)


def _fmt(dt):
    return dt.strftime("%Y-%m-%d %H:%M")


def check_and_send_reminders(state, tg, config, now):
    users = config["users"]
    for task in state["tasks"]:
        if task["status"] != "open":
            continue
        deadline = datetime.fromisoformat(task["deadline"])
        remaining = deadline - now
        sent = set(task.get("reminders_sent", []))
        assignee_name = users.get(task["assignee"], task["assignee"])

        for key, delta in BEFORE_THRESHOLDS:
            if key in sent:
                continue
            if timedelta(0) <= remaining <= delta:
                text = (
                    f"⏰ یادآوری: تسک #{task['id']} برای {assignee_name} "
                    f"تا {_fmt(deadline)} وقت داره.\n{task['description']}"
                )
                tg.send_message(task["chat_id"], text, message_thread_id=task.get("thread_id"))
                sent.add(key)

        if remaining < timedelta(0):
            last = task.get("last_overdue_at")
            last_dt = datetime.fromisoformat(last) if last else None
            if last_dt is None or (now - last_dt) >= OVERDUE_INTERVAL:
                text = (
                    f"⚠️ تسک #{task['id']} برای {assignee_name} از سررسیدش گذشته!\n"
                    f"{task['description']}"
                )
                tg.send_message(task["chat_id"], text, message_thread_id=task.get("thread_id"))
                task["last_overdue_at"] = now.isoformat()

        task["reminders_sent"] = list(sent)
