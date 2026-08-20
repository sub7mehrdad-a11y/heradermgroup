STATUS_LABELS = {"open": "🟡 باز", "done": "✅ انجام شد", "cancelled": "🗑 لغو شده"}
ACTION_LABELS = {"handoff": "ارجاع مجدد", "done": "اتمام"}


def format_task_card(task, users):
    assignee_name = users.get(task["assignee"], task["assignee"])
    status_label = STATUS_LABELS.get(task["status"], task["status"])
    lines = [
        f"📌 {task['title']}",
        f"👤 ارجاع به: {assignee_name}",
        f"🗓 ددلاین: {task['deadline'][:16].replace('T', ' ')}",
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

    lines.append(f"\n#{task['id']}")
    return "\n".join(lines)


def build_keyboard(task, users):
    if task["status"] != "open":
        return None
    other = [u for u in users if u != task["assignee"]]
    buttons = [[{"text": "✅ انجام شد", "callback_data": f"done:{task['id']}"}]]
    if other:
        other_name = users.get(other[0], other[0])
        buttons.append([{"text": f"🔁 ارجاع به {other_name}", "callback_data": f"handoff:{task['id']}"}])
    return {"inline_keyboard": buttons}
