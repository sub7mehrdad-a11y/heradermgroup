import os
import sys

from src.telegram_api import TelegramAPI
from src.storage import load_state, save_state, load_config
from src.commands import process_update
from src.reminders import check_and_send_reminders
from src.date_parser import now_iran

BASE = os.path.dirname(os.path.abspath(__file__))
STATE_PATH = os.path.join(BASE, "data", "tasks.json")
CONFIG_PATH = os.path.join(BASE, "data", "config.json")


def main():
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        print("TELEGRAM_BOT_TOKEN تنظیم نشده.")
        sys.exit(1)

    tg = TelegramAPI(token)
    state = load_state(STATE_PATH)
    config = load_config(CONFIG_PATH)

    offset = state.get("offset", 0) or None
    while True:
        updates = tg.get_updates(offset=offset)
        if not updates:
            break
        for u in updates:
            offset = u["update_id"] + 1
            msg = u.get("message")
            if not msg:
                continue
            replies = process_update(state, config, msg)
            for reply in replies:
                tg.send_message(
                    msg["chat"]["id"], reply, message_thread_id=msg.get("message_thread_id")
                )
        if len(updates) < 100:
            break
    state["offset"] = offset or 0

    check_and_send_reminders(state, tg, config, now_iran())

    save_state(STATE_PATH, state)


if __name__ == "__main__":
    main()
