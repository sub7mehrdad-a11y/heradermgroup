"""Cheap local pre-filter deciding whether a message is worth an AI call.

Two jobs, and the second one matters more than the first:

1. Ordinary chat must never cost a Gemini request. These two talk all day.
2. Ordinary chat must never become a task. In a live run against the real
   group, "سفارش ندادم هنوز" and "امروز ارسال نشده پس" both became tasks,
   because this filter used to treat everyday shop vocabulary ("سفارش",
   "ارسال", "امروز") as evidence of an assignment. A false task is worse
   than a missed one: it clutters the topic and nags every six hours.

So a message now only reaches the model if it either names the other
person or contains an unambiguous imperative. A time word alone proves
nothing — this group says "امروز" constantly about things that already
happened. Anything this filter drops can still be filed with /assign.
"""

# Imperative verb forms and explicit request words only. Deliberately no
# bare nouns ("سفارش", "ارسال", "فاکتور"): those are what these two discuss
# all day and they carry no instruction on their own.
REQUEST_HINTS = (
    "لطفا", "لطفاً", "باید", "یادت نره", "یادت باشه", "فراموش نکن",
    "بفرست", "بفرستید", "ارسال کن", "چک کن", "چک کنید", "بررسی کن",
    "پیگیری کن", "آماده کن", "اماده کن", "انجام بده", "انجام بدید",
    "اضافه کن", "درست کن", "تماس بگیر", "هماهنگ کن", "ثبت کن", "ثبت کنید",
    "بزن", "قرار بده", "قرار بدید", "وارد کن", "به‌روز کن", "بروز کن",
)

MIN_LENGTH = 12


def looks_like_task(text, users):
    """True if `text` plausibly assigns work and deserves an AI call."""
    if not text or len(text) < MIN_LENGTH:
        return False

    lowered = text.lower()

    for username, display_name in users.items():
        if username in lowered:
            return True
        # Persian vocative often appends a letter ("فرزان" -> "فرزانه"),
        # so match the name as a prefix rather than a whole word.
        if display_name and display_name in text:
            return True

    return any(hint in text for hint in REQUEST_HINTS)
