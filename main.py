import argparse
import json
import os
import signal
import subprocess
import sys
import time

from src.telegram_api import TelegramAPI
from src.storage import load_state, save_state, load_config
from src.commands import process_update, mark_done, handoff_task, set_deadline
from src.ai_flow import handle_free_text, handle_dm_text
from src.reminders import check_and_send_reminders
from src.date_parser import now_iran, parse_deadline
from src.task_card import format_task_card, build_keyboard

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE, "data", "tasks.json")
CONFIG_PATH = os.path.join(BASE, "data", "config.json")
ERROR_LOG_PATH = os.path.join(BASE, "data", "last_error.log")

LONG_POLL_SECONDS = 30
COMMIT_DEBOUNCE_SECONDS = 120
MAX_CONSECUTIVE_ERRORS = 6

# Maps a deadline button's callback code to a phrase parse_deadline understands.
DEADLINE_OPTIONS = {
    "today": "امروز",
    "tomorrow": "فردا",
    "2days": "2 روز دیگر",
    "week": "7 روز دیگر",
}

_stop = False


def _request_stop(signum, frame):
    global _stop
    _stop = True


def _fingerprint(state):
    return json.dumps(state, sort_keys=True, ensure_ascii=False)


def _find_task(state, task_id):
    return next((t for t in state["tasks"] if t["id"] == task_id), None)


DM_HEADER = "🔔 تسک جدید برای تو در گروه:\n\n"


def _mirror_to_assignee_dm(tg, state, config, task):
    """Put a copy of the card in the assignee's private chat so they see the
    task without opening the group, and can close it from there."""
    dm_chat_id = state.get("dm_chats", {}).get(task["assignee"])
    if not dm_chat_id or dm_chat_id == task["chat_id"]:
        return
    task.setdefault("dm_message_ids", {})
    if task["assignee"] in task["dm_message_ids"]:
        return
    users = config["users"]
    try:
        result = tg.send_message(
            dm_chat_id,
            DM_HEADER + format_task_card(task, users),
            reply_markup=build_keyboard(task, users),
        )
    except Exception as e:
        # Most likely the user never pressed /start, or blocked the bot.
        print("dm mirror failed:", e)
        return
    if result:
        task["dm_message_ids"][task["assignee"]] = result.get("message_id")


def _refresh_card(tg, state, config, task_id):
    """Re-render every copy of a task's card — the one in the group topic and
    any in private chats — so they never disagree about its status."""
    task = _find_task(state, task_id)
    if task is None:
        return
    users = config["users"]
    body = format_task_card(task, users)
    keyboard = build_keyboard(task, users)

    if task.get("task_message_id"):
        try:
            tg.edit_message_text(task["chat_id"], task["task_message_id"], body, reply_markup=keyboard)
        except Exception as e:
            print("edit failed (group):", e)

    for username, message_id in (task.get("dm_message_ids") or {}).items():
        dm_chat_id = state.get("dm_chats", {}).get(username)
        if not dm_chat_id:
            continue
        try:
            tg.edit_message_text(dm_chat_id, message_id, DM_HEADER + body, reply_markup=keyboard)
        except Exception as e:
            print("edit failed (dm):", e)

    # A handoff moves the task to someone who may not have a copy yet.
    if task["status"] == "open":
        _mirror_to_assignee_dm(tg, state, config, task)


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
                _mirror_to_assignee_dm(tg, state, config, task)


def _handle_callback(state, config, tg, cq):
    data = cq.get("data", "")
    from_user = cq.get("from", {}) or {}
    username = (from_user.get("username") or "").lower()
    users = config["users"]

    if username not in users or ":" not in data:
        tg.answer_callback_query(cq["id"])
        return

    action, _, rest = data.partition(":")
    id_text, _, option = rest.partition(":")
    try:
        task_id = int(id_text)
    except ValueError:
        tg.answer_callback_query(cq["id"])
        return

    if action == "done":
        ok, msg, _task = mark_done(state, task_id, username, "")
    elif action == "handoff":
        ok, msg, _task = handoff_task(state, config, task_id, username, "")
    elif action == "dl":
        deadline = parse_deadline(DEADLINE_OPTIONS.get(option, ""))
        if deadline is None:
            ok, msg = False, "گزینه ددلاین نامعتبر است."
        else:
            ok, msg, _task = set_deadline(state, task_id, username, deadline)
    else:
        ok, msg = False, None

    tg.answer_callback_query(cq["id"], text=(msg[:190] if msg else None))
    if ok:
        _refresh_card(tg, state, config, task_id)


def _handle_private(state, config, tg, msg, gemini_key):
    from_user = msg.get("from", {}) or {}
    username = (from_user.get("username") or "").lower()
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()

    state.setdefault("dm_chats", {})
    state["dm_chats"][username] = chat_id

    if text == "/start":
        tg.send_message(
            chat_id,
            "ثبت شد ✅ از این به بعد تسک‌های جدید و یادآوری‌هاشون رو همینجا هم برات می‌فرستم.\n"
            "می‌تونی همینجا جواب بدی یا دکمه «انجام شد» رو بزنی.",
        )
        return

    if text.startswith("/"):
        items = process_update(state, config, msg)
    else:
        items = handle_dm_text(state, config, msg, gemini_key)

    _send_items(tg, state, config, chat_id, None, items)


def _process_updates(tg, state, config, gemini_key, updates):
    for u in updates:
        state["offset"] = u["update_id"] + 1

        cq = u.get("callback_query")
        if cq:
            _handle_callback(state, config, tg, cq)
            continue

        msg = u.get("message")
        if not msg:
            continue

        if msg.get("chat", {}).get("type") == "private":
            from_user = msg.get("from", {}) or {}
            if (from_user.get("username") or "").lower() in config["users"]:
                _handle_private(state, config, tg, msg, gemini_key)
            continue

        text = (msg.get("text") or "").strip()
        if text.startswith("/"):
            items = process_update(state, config, msg)
        else:
            items = handle_free_text(state, config, msg, gemini_key)

        _send_items(tg, state, config, msg["chat"]["id"], msg.get("message_thread_id"), items)


def _git(*args):
    return subprocess.run(
        ["git"] + list(args), cwd=BASE,
        capture_output=True, text=True, timeout=120,
    )


def _git_sync():
    """Persist the state file back to the repo. Best-effort: a git failure
    must never take the bot down, since state is re-read from disk anyway
    and the next sync will carry it."""
    try:
        if not _git("diff", "--quiet", "--", "data/").returncode:
            return False
        _git("add", "data/")
        _git("commit", "-m", "chore: update task state")
        push = _git("push")
        if push.returncode:
            # Someone else (a previous run) pushed first — rebase and retry once.
            _git("pull", "--rebase")
            push = _git("push")
            if push.returncode:
                print("git push failed:", push.stderr.strip()[:300])
                return False
        return True
    except Exception as e:
        print("git sync error:", e)
        return False


def _force_utf8_output():
    """Windows consoles default to cp1252, which raises UnicodeEncodeError on
    any Persian print(). Harmless on the Linux CI runner, fatal locally."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def main():
    _force_utf8_output()
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--loop", type=int, default=0, metavar="SECONDS",
        help="stay connected and respond in real time for this many seconds",
    )
    parser.add_argument(
        "--git-sync", action="store_true",
        help="commit and push the state file from inside the loop",
    )
    args = parser.parse_args()

    token = (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()
    gemini_key = (os.environ.get("GEMINI_API_KEY") or "").strip()

    if not token:
        print(
            "خطا: TELEGRAM_BOT_TOKEN خالی است.\n"
            "  → Settings → Secrets and variables → Actions → تب Secrets (نه Variables)\n"
            "  → دکمه New repository secret\n"
            "  → Name دقیقاً: TELEGRAM_BOT_TOKEN\n"
            "دقت کن Secret باید روی همین ریپو ساخته بشه؛ Secretهای ریپوهای دیگه اینجا دیده نمی‌شن."
        )
        sys.exit(1)

    if not gemini_key:
        # Not fatal: slash commands still work, only free-text parsing is off.
        print("هشدار: GEMINI_API_KEY خالی است — تشخیص متن آزاد غیرفعال می‌ماند، "
              "ولی دستورهایی مثل /assign و /done کار می‌کنند.")

    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)

    tg = TelegramAPI(token)
    state = load_state(STATE_PATH)
    config = load_config(CONFIG_PATH)

    deadline = time.monotonic() + args.loop if args.loop else None
    poll_timeout = LONG_POLL_SECONDS if args.loop else 0
    last_saved = _fingerprint(state)
    last_commit = time.monotonic()

    consecutive_errors = 0
    recent_errors = []
    while True:
        updates = []
        try:
            updates = tg.get_updates(
                offset=state.get("offset") or None, timeout=poll_timeout
            )
            _process_updates(tg, state, config, gemini_key, updates)
            check_and_send_reminders(state, tg, config, now_iran())
            consecutive_errors = 0
        except Exception as e:
            consecutive_errors += 1
            detail = f"{now_iran().isoformat()} attempt {consecutive_errors}: {e!r}"
            print("cycle error:", detail, flush=True)
            recent_errors.append(detail)
            # Fail loudly rather than idling for the rest of the job window
            # pretending to work — a silently-broken bot is what hid this.
            if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                print(f"خطا: {consecutive_errors} بار پشت سر هم اتصال شکست خورد.", flush=True)
                # Written into the repo because the Actions job log needs a
                # token to fetch, while the committed file does not.
                with open(ERROR_LOG_PATH, "w", encoding="utf-8") as f:
                    f.write("\n".join(recent_errors) + "\n")
                save_state(STATE_PATH, state)
                if args.git_sync:
                    _git_sync()
                sys.exit(1)
            time.sleep(5)

        current = _fingerprint(state)
        if current != last_saved:
            save_state(STATE_PATH, state)
            last_saved = current

        if not args.loop:
            if not updates:
                break  # single-pass mode: keep draining until the queue is empty
            continue
        if _stop or time.monotonic() >= deadline:
            break
        if args.git_sync and (time.monotonic() - last_commit) >= COMMIT_DEBOUNCE_SECONDS:
            _git_sync()
            last_commit = time.monotonic()

    save_state(STATE_PATH, state)
    if args.git_sync:
        _git_sync()


if __name__ == "__main__":
    main()
