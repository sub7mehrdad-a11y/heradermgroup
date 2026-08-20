import json
import os

DEFAULT_STATE = {"offset": 0, "next_id": 1, "tasks": []}


def load_state(path):
    if not os.path.exists(path):
        return dict(DEFAULT_STATE)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_state(path, state):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
        f.write("\n")


def load_config(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
