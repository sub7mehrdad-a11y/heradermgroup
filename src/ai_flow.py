from .gemini_client import extract_task, classify_followup
from .date_parser import parse_deadline, now_iran
from .commands import create_task, mark_done, handoff_task
from .task_card import format_task_card, build_keyboard
from .task_hint import looks_like_task

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


def handle_free_text(state, config, msg, api_key):
    """Handle a non-command message via Gemini: either as a follow-up
    (done/handoff) to the sender's own open task in this topic, or as a
    brand-new task. Ordinary chat is filtered out locally first so it never
    costs an API call.
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

    candidate = _find_open_task_for(state, chat_id, thread_id, username)
    if candidate:
        result = classify_followup(api_key, text, candidate, users)
        if result and result.get("type") == "done":
            ok, reply, _task = mark_done(state, candidate["id"], username, result.get("note", ""))
            if ok:
                return [{"text": reply}, {"edit_task_id": candidate["id"]}]
        elif result and result.get("type") == "handoff":
            ok, reply, _task = handoff_task(
                state, config, candidate["id"], username, result.get("note", "")
            )
            if ok:
                return [{"text": reply}, {"edit_task_id": candidate["id"]}]

    if not looks_like_task(text, users):
        return []

    extracted = extract_task(api_key, text, username, users, now_iran().isoformat())
    if extracted is None:
        return [{"text": AI_DOWN_NOTICE}]
    if not extracted.get("is_task"):
        return []

    phrase = (extracted.get("deadline_phrase") or "").strip()
    deadline = parse_deadline(phrase) if phrase else None

    task = create_task(
        state, chat_id, thread_id,
        creator=username, assignee=extracted["assignee"],
        title=extracted["title"], description=extracted.get("description", ""),
        deadline=deadline,
    )
    return _card_items(task, users)
