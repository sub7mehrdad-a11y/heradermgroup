import json
import time

import requests

MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest"]
API_ROOT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
RETRY_DELAYS = [0, 15, 45]


def _call_gemini(api_key, model, prompt):
    url = API_ROOT.format(model=model)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    r = requests.post(url, params={"key": api_key}, json=body, timeout=30)
    r.raise_for_status()
    data = r.json()
    return data["candidates"][0]["content"]["parts"][0]["text"]


def _extract_json(raw):
    text = raw.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start:end + 1])
    except (json.JSONDecodeError, ValueError):
        return None


def _ask_json(api_key, prompt):
    """Try each model with backoff. Returns a parsed dict, or None on total
    failure — never fabricates a result, matching the project's existing
    'skip rather than degrade' rule for LLM calls."""
    if not api_key:
        return None
    for model in MODELS:
        for delay in RETRY_DELAYS:
            if delay:
                time.sleep(delay)
            try:
                raw = _call_gemini(api_key, model, prompt)
            except Exception:
                continue
            parsed = _extract_json(raw)
            if parsed is not None:
                return parsed
    return None


NOT_A_TASK = {"is_task": False}


def extract_task(api_key, text, sender_username, users, now_iso):
    """Returns a task dict, NOT_A_TASK, or None when the API itself failed.

    Callers must distinguish the last case: "the model is unreachable" needs
    to be reported to the user, while "this isn't a task" must stay silent.
    """
    names = "، ".join(f'"{u}" ({name})' for u, name in users.items())
    prompt = f"""شما دستیار پردازش پیام‌های یک گروه کاری دو نفره هستید.
افراد گروه: {names}
این پیام رو الان کاربر «{sender_username}» نوشته.
زمان الان: {now_iso} (به وقت ایران)

متن پیام:
\"\"\"{text}\"\"\"

اگر این پیام یک کار/وظیفه برای یکی از این دو نفر توصیف می‌کنه (حتی اگر ددلاین ذکر نشده باشه)،
فقط یک JSON خام (بدون Markdown، بدون توضیح اضافه) با این ساختار دقیق برگردون:
{{"is_task": true, "assignee": "<یوزرنیم دقیق مسئول کار، از بین {list(users.keys())}>", "title": "<عنوان کوتاه فارسی، حداکثر ۸ کلمه>", "description": "<توضیح کامل‌تر کار>", "deadline_phrase": "<عبارت ددلاین دقیقاً به همان شکلی که در پیام آمده، یا رشته خالی اگر ددلاینی ذکر نشده>"}}

نکته مهم درباره مسئول کار: اگر پیام خطاب به نفر مقابل نوشته شده (مثلاً با صدا زدن اسمش یا لحن درخواستی)،
مسئول کار اون نفره، نه نویسنده پیام. فقط اگر نویسنده صراحتاً از کار خودش حرف می‌زنه، مسئول خودشه.

اگر پیام اصلاً کار/وظیفه‌ای رو توصیف نمی‌کنه (چت عادی، سوال، نظر، گزارش)، فقط برگردون:
{{"is_task": false}}
"""
    result = _ask_json(api_key, prompt)
    if result is None:
        return None  # model unreachable — caller surfaces this
    if not result.get("is_task"):
        return NOT_A_TASK
    if result.get("assignee") not in users:
        return NOT_A_TASK
    return result


def classify_followup(api_key, text, task, users):
    assignee_name = users.get(task["assignee"], task["assignee"])
    prompt = f"""این پیام ممکنه پاسخ به یک تسک باز باشه.
تسک: «{task['title']}»
توضیح تسک: «{task.get('description', '')}»
مسئول فعلی تسک: {assignee_name}

متن پیام تازه:
\"\"\"{text}\"\"\"

فقط یک JSON خام برگردون:
- اگر پیام می‌گه کل کار تموم و تحویل داده شده: {{"type": "done", "note": "<خلاصه نتیجه، اگر ذکر شده وگرنه رشته خالی>"}}
- اگر پیام می‌گه بخشی از کار انجام شده و بقیه‌اش رو به نفر دیگه ارجاع می‌ده: {{"type": "handoff", "note": "<خلاصه‌ی اینکه چی انجام شده و چی مونده>"}}
- اگر این پیام ربطی به تکمیل یا ارجاع این تسک خاص نداره (چت عادی، سوال، تسک دیگه): {{"type": "none"}}
"""
    result = _ask_json(api_key, prompt)
    if not result or result.get("type") not in ("done", "handoff", "none"):
        return None
    return result
