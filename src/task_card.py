STATUS_LABELS = {"open": "🟡 باز", "done": "✅ انجام شد", "cancelled": "🗑 لغو شده"}
ACTION_LABELS = {"handoff": "ارجاع مجدد", "done": "اتمام"}

DEADLINE_CHOICES = [
    ("today", "امروز"),
    ("tomorrow", "فردا"),
    ("2days", "۲ روز دیگه"),
    ("week", "یک هفته"),
]


def format_task_card(task, users):
    assignee_name = users.get(task["assignee"], task["assignee"])
    status_label = STATUS_LABELS.get(task["status"], task["status"])
    deadline = task.get("deadline")
    deadline_label = deadline[:16].replace("T", " ") if deadline else "تعیین نشده"

    lines = [
        f"📌 {task['title']}",
        f"👤 ارجاع به: {assignee_name}",
        f"🗓 ددلاین: {deadline_label}",
    ]
    if task.get("description") and task["description"] != task["title"]:
        lines.append(f"📝 {task['description']}")
    lines.append(f"وضعیت: {status_label}")

    history = task.get("history", [])
    if len(history) > 1:
        lines.append("")
        lines.append("تاریخچه:")
        for h in history[1:]:
            actor_name = users.get(h["actor"], h["actor"])
            action_label = ACTION_LABELS.get(h["action"], h["action"])
            note = f" — {h['note']}" if h.get("note") else ""
            lines.append(f"• {actor_name} ({action_label}){note}")

    if not deadline and task["status"] == "open":
        lines.append("")
        lines.append("ددلاین مشخص نشده — با دکمه‌های زیر تعیینش کن.")

    lines.append(f"\n#{task['id']}")
    return "\n".join(lines)


def build_keyboard(task, users):
    if task["status"] != "open":
        return None

    buttons = []
    if not task.get("deadline"):
        buttons.append([
            {"text": label, "callback_data": f"dl:{task['id']}:{code}"}
            for code, label in DEADLINE_CHOICES[:2]
        ])
        buttons.append([
            {"text": label, "callback_data": f"dl:{task['id']}:{code}"}
            for code, label in DEADLINE_CHOICES[2:]
        ])

    buttons.append([{"text": "✅ انجام شد", "callback_data": f"done:{task['id']}"}])
    other = [u for u in users if u != task["assignee"]]
    if other:
        other_name = users.get(other[0], other[0])
        buttons.append([{"text": f"🔁 ارجاع به {other_name}", "callback_data": f"handoff:{task['id']}"}])
    return {"inline_keyboard": buttons}
