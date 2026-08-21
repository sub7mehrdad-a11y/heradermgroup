from .date_parser import parse_deadline, now_iran
from .task_card import format_task_card, build_keyboard

HELP_TEXT = (
    "راهنمای ربات وظایف:\n\n"
    "می‌تونی معمولی و فارسی بنویسی (مثلاً «فرزان فردا ساعت ۶ باید فاکتورها رو بفرسته») "
    "و هوش مصنوعی خودش تبدیلش می‌کنه به تسک. ذکر ددلاین اجباری نیست — "
    "اگه ننویسی، با دکمه‌های روی کارت تعیینش می‌کنی.\n\n"
    "یا از این دستورهای مطمئن استفاده کن:\n"
    "/task [ددلاین |] <شرح کار>    → تسک برای خودت\n"
    "/assign [ددلاین |] <شرح کار>  → تسک برای طرف مقابل (ارجاع)\n"
    "/done <شماره> [یادداشت]       → تسک رو انجام‌شده کن\n"
    "/handoff <شماره> | <یادداشت>  → بخشی از کار رو انجام دادی، بقیه رو ارجاع بده\n"
    "/tasks                        → تسک‌های باز خودت\n"
    "/alltasks                     → همه‌ی تسک‌های باز\n"
    "/cancel <شماره>               → لغو تسک (فقط سازنده)\n"
    "/help                         → همین راهنما\n\n"
    "نمونه ددلاین: امروز 18:00 | فردا | فردا 9 | پس‌فردا | 2 روز دیگر | 3 ساعت دیگر | 2026-08-25 14:00"
)


def _text(s):
    return {"text": s}


def _other_user(username, users):
    keys = list(users.keys())
    if len(keys) != 2:
        return None
    return keys[0] if username == keys[1] else keys[1]


def _find_task(state, task_id):
    return next((t for t in state["tasks"] if t["id"] == task_id), None)


def _fmt_dt(iso_text):
    if not iso_text:
        return "تعیین نشده"
    return iso_text[:16].replace("T", " ")


def _deadline_sort_key(task):
    """Tasks with no deadline sort last rather than raising on None < str."""
    deadline = task.get("deadline")
    return (deadline is None, deadline or "")


def create_task(state, chat_id, thread_id, creator, assignee, title, description, deadline):
    """`deadline` may be None — a task assigned without one is still a real
    task, and the card offers buttons to set it afterwards."""
    now = now_iran().isoformat()
    task = {
        "id": state["next_id"],
        "title": title,
        "description": description or "",
        "creator": creator,
        "assignee": assignee,
        "chat_id": chat_id,
        "thread_id": thread_id,
        "created_at": now,
        "deadline": deadline.isoformat() if deadline else None,
        "status": "open",
        "history": [{"actor": creator, "action": "create", "note": None, "at": now}],
        "last_reminder_at": None,
        "done_at": None,
        "task_message_id": None,
    }
    state["tasks"].append(task)
    state["next_id"] += 1
    return task


def set_deadline(state, task_id, actor, deadline):
    task = _find_task(state, task_id)
    if task is None:
        return False, f"تسک #{task_id} پیدا نشد.", None
    if task["status"] != "open":
        return False, f"تسک #{task_id} از قبل بسته شده.", None
    task["deadline"] = deadline.isoformat()
    task["last_reminder_at"] = None
    return True, f"🗓 ددلاین تسک #{task_id} روی {deadline.strftime('%Y-%m-%d %H:%M')} تنظیم شد.", task


def mark_done(state, task_id, actor, note):
    task = _find_task(state, task_id)
    if task is None:
        return False, f"تسک #{task_id} پیدا نشد.", None
    if task["status"] != "open":
        return False, f"تسک #{task_id} از قبل بسته شده.", None
    now = now_iran().isoformat()
    task["status"] = "done"
    task["done_at"] = now
    task["history"].append({"actor": actor, "action": "done", "note": note or None, "at": now})
    return True, f"🎉 تسک #{task_id} تموم شد!\n{task['title']}", task


def handoff_task(state, config, task_id, actor, note):
    task = _find_task(state, task_id)
    if task is None:
        return False, f"تسک #{task_id} پیدا نشد.", None
    if task["status"] != "open":
        return False, f"تسک #{task_id} از قبل بسته شده.", None
    users = config["users"]
    other = _other_user(task["assignee"], users)
    if other is None:
        return False, "طرف مقابل پیدا نشد.", None
    task["assignee"] = other
    task["last_reminder_at"] = None
    task["history"].append({
        "actor": actor, "action": "handoff", "note": note or None, "at": now_iran().isoformat()
    })
    new_name = users.get(other, other)
    return True, f"🔁 تسک #{task_id} ارجاع شد به {new_name}.", task


def process_update(state, config, msg):
    """Handle one command message (leading '/'). Mutates state in place.
    Returns a list of outgoing items: {"text": ...} to send a new message,
    or {"edit_task_id": id} to refresh that task's existing card in place.
    """
    text = (msg.get("text") or "").strip()
    if not text.startswith("/"):
        return []

    from_user = msg.get("from", {}) or {}
    username = (from_user.get("username") or "").lower()
    users = config["users"]
    if username not in users:
        return []

    chat_id = msg["chat"]["id"]
    thread_id = msg.get("message_thread_id")

    parts = text.split(maxsplit=1)
    cmd = parts[0].split("@")[0].lower()
    rest = parts[1] if len(parts) > 1 else ""

    if cmd in ("/start", "/help"):
        return [_text(HELP_TEXT)]

    if cmd in ("/task", "/assign"):
        if "|" in rest:
            deadline_text, desc = (p.strip() for p in rest.split("|", 1))
        else:
            # No "|" means no deadline was given — still a valid task, the
            # card will offer buttons to set one.
            deadline_text, desc = "", rest.strip()
        if not desc:
            return [_text("شرح کار رو ننوشتی.\nنمونه: /assign فردا 18:00 | تماس با تامین‌کننده")]
        deadline = parse_deadline(deadline_text) if deadline_text else None
        if deadline_text and deadline is None:
            return [_text(f"ددلاین «{deadline_text}» فهمیده نشد. نمونه: فردا 18:00 / امروز / 2 روز دیگر")]
        assignee = username if cmd == "/task" else _other_user(username, users)
        if assignee is None:
            return [_text("نمی‌تونم طرف مقابل رو پیدا کنم.")]
        title = desc if len(desc) <= 40 else desc[:37] + "..."
        task = create_task(state, chat_id, thread_id, username, assignee, title, desc, deadline)
        return [{
            "text": format_task_card(task, users),
            "reply_markup": build_keyboard(task, users),
            "attach_task_id": task["id"],
        }]

    if cmd == "/done":
        if not rest:
            return [_text("شماره تسک رو بنویس: /done 3")]
        bits = rest.split(maxsplit=1)
        try:
            task_id = int(bits[0])
        except ValueError:
            return [_text("شماره تسک نامعتبره.")]
        note = bits[1] if len(bits) > 1 else ""
        ok, reply, _task = mark_done(state, task_id, username, note)
        items = [_text(reply)]
        if ok:
            items.append({"edit_task_id": task_id})
        return items

    if cmd == "/handoff":
        if "|" not in rest:
            return [_text("فرمت درست: /handoff شماره | یادداشت")]
        id_text, note = (p.strip() for p in rest.split("|", 1))
        try:
            task_id = int(id_text)
        except ValueError:
            return [_text("شماره تسک نامعتبره.")]
        ok, reply, _task = handoff_task(state, config, task_id, username, note)
        items = [_text(reply)]
        if ok:
            items.append({"edit_task_id": task_id})
        return items

    if cmd == "/cancel":
        if not rest.strip():
            return [_text("شماره تسک رو بنویس: /cancel 3")]
        try:
            task_id = int(rest.strip())
        except ValueError:
            return [_text("شماره تسک نامعتبره.")]
        task = _find_task(state, task_id)
        if task is None:
            return [_text(f"تسک #{task_id} پیدا نشد.")]
        if task["creator"] != username:
            return [_text("فقط سازنده‌ی تسک می‌تونه لغوش کنه.")]
        if task["status"] != "open":
            return [_text(f"تسک #{task_id} از قبل بسته شده.")]
        task["status"] = "cancelled"
        return [_text(f"🗑 تسک #{task_id} لغو شد."), {"edit_task_id": task_id}]

    if cmd == "/tasks":
        mine = [t for t in state["tasks"] if t["status"] == "open" and t["assignee"] == username]
        if not mine:
            return [_text("تسک باز نداری. 🎉")]
        lines = ["تسک‌های باز تو:"]
        for t in sorted(mine, key=_deadline_sort_key):
            lines.append(f"#{t['id']} — {t['title']} (موعد: {_fmt_dt(t.get('deadline'))})")
        return [_text("\n".join(lines))]

    if cmd == "/alltasks":
        open_tasks = [t for t in state["tasks"] if t["status"] == "open"]
        if not open_tasks:
            return [_text("هیچ تسک بازی نیست. 🎉")]
        lines = ["همه‌ی تسک‌های باز:"]
        for t in sorted(open_tasks, key=_deadline_sort_key):
            who = users.get(t["assignee"], t["assignee"])
            lines.append(f"#{t['id']} — {t['title']} → {who} (موعد: {_fmt_dt(t.get('deadline'))})")
        return [_text("\n".join(lines))]

    return [_text(f"دستور ناشناخته: {cmd}\n/help رو بزن برای راهنما.")]
