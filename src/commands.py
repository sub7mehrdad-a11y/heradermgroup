from .date_parser import parse_deadline, now_iran

HELP_TEXT = (
    "راهنمای ربات وظایف:\n\n"
    "/task <ددلاین> | <شرح کار>    → تسک برای خودت\n"
    "/assign <ددلاین> | <شرح کار>  → تسک برای طرف مقابل (ارجاع)\n"
    "/done <شماره> [یادداشت]       → تسک رو انجام‌شده کن\n"
    "/tasks                        → تسک‌های باز خودت\n"
    "/alltasks                     → همه‌ی تسک‌های باز\n"
    "/cancel <شماره>               → لغو تسک (فقط سازنده)\n"
    "/help                         → همین راهنما\n\n"
    "نمونه ددلاین: امروز 18:00 | فردا | فردا 9 | پس‌فردا | 2 روز دیگر | 3 ساعت دیگر | 2026-08-25 14:00\n\n"
    "مثال کامل:\n/assign فردا 18:00 | تماس با تامین‌کننده"
)


def _other_user(username, users):
    keys = list(users.keys())
    if len(keys) != 2:
        return None
    return keys[0] if username == keys[1] else keys[1]


def _fmt_dt(iso_text):
    return iso_text[:16].replace("T", " ")


def process_update(state, config, msg):
    """Handle one incoming Telegram message. Mutates state in place.
    Returns a list of reply strings to send back in the same chat/thread.
    """
    text = (msg.get("text") or "").strip()
    if not text.startswith("/"):
        return []

    from_user = msg.get("from", {}) or {}
    username = (from_user.get("username") or "").lower()
    users = config["users"]
    if username not in users:
        return []  # not one of the two participants — ignore silently

    parts = text.split(maxsplit=1)
    cmd = parts[0].split("@")[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if cmd in ("/start", "/help"):
        return [HELP_TEXT]

    if cmd in ("/task", "/assign"):
        if "|" not in rest:
            return ["فرمت درست: /task ددلاین | شرح کار\n/help رو بزن برای نمونه‌ها."]
        deadline_text, desc = (p.strip() for p in rest.split("|", 1))
        if not desc:
            return ["شرح کار رو ننوشتی."]
        deadline = parse_deadline(deadline_text)
        if deadline is None:
            return [f"ددلاین «{deadline_text}» فهمیده نشد. نمونه: فردا 18:00 / امروز / 2 روز دیگر"]
        if cmd == "/task":
            assignee = username
        else:
            assignee = _other_user(username, users)
            if assignee is None:
                return ["نمی‌تونم طرف مقابل رو پیدا کنم."]
        task = {
            "id": state["next_id"],
            "description": desc,
            "creator": username,
            "assignee": assignee,
            "chat_id": msg["chat"]["id"],
            "thread_id": msg.get("message_thread_id"),
            "created_at": now_iran().isoformat(),
            "deadline": deadline.isoformat(),
            "status": "open",
            "reminders_sent": [],
            "last_overdue_at": None,
            "done_at": None,
            "done_note": None,
        }
        state["tasks"].append(task)
        state["next_id"] += 1
        assignee_name = users.get(assignee, assignee)
        return [
            f"✅ تسک #{task['id']} ثبت شد برای {assignee_name}\n"
            f"موعد: {deadline.strftime('%Y-%m-%d %H:%M')}\n{desc}"
        ]

    if cmd == "/done":
        if not rest:
            return ["شماره تسک رو بنویس: /done 3"]
        bits = rest.split(maxsplit=1)
        try:
            task_id = int(bits[0])
        except ValueError:
            return ["شماره تسک نامعتبره."]
        note = bits[1] if len(bits) > 1 else ""
        task = next((t for t in state["tasks"] if t["id"] == task_id), None)
        if task is None:
            return [f"تسک #{task_id} پیدا نشد."]
        if task["status"] != "open":
            return [f"تسک #{task_id} از قبل بسته شده."]
        task["status"] = "done"
        task["done_at"] = now_iran().isoformat()
        task["done_note"] = note
        reply = f"🎉 تسک #{task_id} تموم شد!\n{task['description']}"
        if note:
            reply += f"\nیادداشت: {note}"
        return [reply]

    if cmd == "/cancel":
        if not rest.strip():
            return ["شماره تسک رو بنویس: /cancel 3"]
        try:
            task_id = int(rest.strip())
        except ValueError:
            return ["شماره تسک نامعتبره."]
        task = next((t for t in state["tasks"] if t["id"] == task_id), None)
        if task is None:
            return [f"تسک #{task_id} پیدا نشد."]
        if task["creator"] != username:
            return ["فقط سازنده‌ی تسک می‌تونه لغوش کنه."]
        if task["status"] != "open":
            return [f"تسک #{task_id} از قبل بسته شده."]
        task["status"] = "cancelled"
        return [f"🗑 تسک #{task_id} لغو شد."]

    if cmd == "/tasks":
        mine = [t for t in state["tasks"] if t["status"] == "open" and t["assignee"] == username]
        if not mine:
            return ["تسک باز نداری. 🎉"]
        lines = ["تسک‌های باز تو:"]
        for t in sorted(mine, key=lambda x: x["deadline"]):
            lines.append(f"#{t['id']} — {t['description']} (موعد: {_fmt_dt(t['deadline'])})")
        return ["\n".join(lines)]

    if cmd == "/alltasks":
        open_tasks = [t for t in state["tasks"] if t["status"] == "open"]
        if not open_tasks:
            return ["هیچ تسک بازی نیست. 🎉"]
        lines = ["همه‌ی تسک‌های باز:"]
        for t in sorted(open_tasks, key=lambda x: x["deadline"]):
            who = users.get(t["assignee"], t["assignee"])
            lines.append(f"#{t['id']} — {t['description']} → {who} (موعد: {_fmt_dt(t['deadline'])})")
        return ["\n".join(lines)]

    return [f"دستور ناشناخته: {cmd}\n/help رو بزن برای راهنما."]
