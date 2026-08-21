from .gemini_client import extract_task, classify_followup
from .date_parser import parse_deadline, now_iran
from .commands import create_task, mark_done, handoff_task
from .task_card import format_task_card, build_keyboard
from .task_hint import looks_like_task, looks_like_followup

THINKING_NOTICE = "⏳ دارم بررسی می‌کنم…"

AI_DOWN_NOTICE = (
    "به نظر می‌رسه این پیام یک تسکه، ولی الان نتونستم به هوش مصنوعی وصل بشم.\n"
    "لطفاً دستی ثبتش کن:\n/assign فردا 18:00 | شرح کار"
)


def _find_open_task_for(state, chat_id, thread_id, username):
    candidates = [
        t for t in state["tasks"]
        if t["status"] == "open" and t["chat_id"] == chat_id
        and t.get("thread_id") == thread_id and t["assignee"] == username
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda t: t["created_at"])[-1]


def _card_items(task, users):
    return [{
        "text": format_task_card(task, users),
        "reply_markup": build_keyboard(task, users),
        "attach_task_id": task["id"],
    }]


def _open_tasks_for(state, username):
    return [t for t in state["tasks"] if t["status"] == "open" and t["assignee"] == username]


def _task_list_lines(tasks):
    return "\n".join(f"#{t['id']} — {t['title']}" for t in tasks)


def handle_dm_text(state, config, msg, api_key):
    """A private message is always addressed to the bot, so unlike the group
    this never stays silent — the user gets an answer either way."""
    text = (msg.get("text") or "").strip()
    if not text:
        return []

    username = ((msg.get("from") or {}).get("username") or "").lower()
    users = config["users"]
    if username not in users:
        return []

    open_tasks = _open_tasks_for(state, username)
    if not open_tasks:
        return [{"text": "الان تسک بازی نداری. 🎉"}]

    explicit = None
    for t in open_tasks:
        if f"#{t['id']}" in text or text.split()[0].strip("#:.") == str(t["id"]):
            explicit = t
            break

    if explicit is not None:
        target = explicit
    elif len(open_tasks) == 1:
        target = open_tasks[0]
    else:
        return [{
            "text": "چند تا تسک باز داری — بگو کدوم:\n"
                    + _task_list_lines(open_tasks)
                    + "\n\nشماره‌شو اول پیامت بنویس، مثلاً:\n"
                      f"{open_tasks[0]['id']} انجام شد"
        }]

    if not api_key:
        return [{"text": f"برای بستن تسک #{target['id']} بنویس: /done {target['id']}"}]

    result = classify_followup(api_key, text, target, users)
    if result is None:
        return [{"text": f"الان به هوش مصنوعی وصل نشدم. برای بستن تسک بنویس: /done {target['id']}"}]

    if result.get("type") == "done":
        ok, reply, _t = mark_done(state, target["id"], username, result.get("note", ""))
        if ok:
            return [{"text": reply}, {"edit_task_id": target["id"]}]
    elif result.get("type") == "handoff":
        ok, reply, _t = handoff_task(state, config, target["id"], username, result.get("note", ""))
        if ok:
            return [{"text": reply}, {"edit_task_id": target["id"]}]

    return [{
        "text": f"متوجه نشدم این جواب تسک #{target['id']} رو می‌بنده یا نه.\n"
                f"اگه تمومه بنویس: /done {target['id']} <توضیح>\n"
                f"اگه بخشی‌ش مونده: /handoff {target['id']} | <توضیح>"
    }]


def handle_free_text(state, config, msg, api_key, on_slow=None):
    """Handle a non-command message via Gemini: either as a follow-up
    (done/handoff) to the sender's own open task in this topic, or as a
    brand-new task. Ordinary chat is filtered out locally first so it never
    costs an API call.

    `on_slow` is called just before the first (slow) model request and should
    return the message id of a placeholder posted in the chat. Whatever this
    function returns then replaces or removes that placeholder, so the group
    can see the bot working instead of guessing.
    """
    if not api_key:
        return []
    text = (msg.get("text") or "").strip()
    if not text:
        return []

    from_user = msg.get("from", {}) or {}
    username = (from_user.get("username") or "").lower()
    users = config["users"]
    if username not in users:
        return []

    chat_id = msg["chat"]["id"]
    thread_id = msg.get("message_thread_id")

    is_task_candidate = looks_like_task(text, users)
    candidate = _find_open_task_for(state, chat_id, thread_id, username)
    is_followup_candidate = candidate is not None and looks_like_followup(text)

    if not is_task_candidate and not is_followup_candidate:
        return []

    placeholder_id = on_slow() if on_slow else None

    def finish(items):
        if placeholder_id is None:
            return items
        if not items:
            return [{"delete_message_id": placeholder_id}]
        items[0] = dict(items[0], replace_message_id=placeholder_id)
        return items

    if is_followup_candidate:
        result = classify_followup(api_key, text, candidate, users)
        if result and result.get("type") == "done":
            ok, reply, _task = mark_done(state, candidate["id"], username, result.get("note", ""))
            if ok:
                return finish([{"text": reply}, {"edit_task_id": candidate["id"]}])
        elif result and result.get("type") == "handoff":
            ok, reply, _task = handoff_task(
                state, config, candidate["id"], username, result.get("note", "")
            )
            if ok:
                return finish([{"text": reply}, {"edit_task_id": candidate["id"]}])

    if not is_task_candidate:
        return finish([])

    extracted = extract_task(api_key, text, username, users, now_iran().isoformat())
    if extracted is None:
        return finish([{"text": AI_DOWN_NOTICE}])
    if not extracted.get("is_task"):
        return finish([])

    phrase = (extracted.get("deadline_phrase") or "").strip()
    deadline = parse_deadline(phrase) if phrase else None

    task = create_task(
        state, chat_id, thread_id,
        creator=username, assignee=extracted["assignee"],
        title=extracted["title"], description=extracted.get("description", ""),
        deadline=deadline,
    )
    return finish(_card_items(task, users))
