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

# Words that suggest a message reports progress on work already assigned.
# Without this gate the bot asked the model "is this an answer to your open
# task?" about literally every line the assignee typed, which cost a request
# and several seconds each time.
FOLLOWUP_HINTS = (
    "تموم", "تمام", "انجام شد", "انجام دادم", "فرستادم", "ارسال کردم",
    "ثبت کردم", "ثبت شد", "آماده شد", "آماده‌ست", "امادست", "درست شد",
    "حله", "اوکی", "اوکیه", "شد ", "زدم", "گذاشتم", "قرار دادم",
    "نصفه", "بقیه‌ش", "بقیه اش", "بقیشو", "باهات", "با تو",
)

MIN_LENGTH = 12

# Anything that can sit between the name and the actual request.
_VOCATIVE_LEADS = ("جان", "عزیز", "جون")
_LEADING_JUNK = " \t\n،,.:!-–—@"


def leading_name(text, users):
    """The username a message is addressed to, when it opens with their name.

    This is the agreed convention for filing a task: start the sentence with
    the other person's name. Because it is a plain string match it is exact
    and predictable — and it settles the assignee outright, instead of asking
    the model to infer it. That inference is what once filed "سفارش ندادم
    هنوز" as a task for its own author.
    """
    if not text:
        return None
    head = text.lstrip(_LEADING_JUNK)
    lowered = head.lower()

    for username, display_name in users.items():
        if lowered.startswith(username):
            return username
        if not display_name:
            continue
        # Persian vocative attaches to the name ("فرزان" -> "فرزانه") or
        # follows it as a separate word ("فرزان جان").
        if head.startswith(display_name):
            return username
        for lead in _VOCATIVE_LEADS:
            if head.startswith(f"{display_name}{lead}") or head.startswith(f"{display_name} {lead}"):
                return username
    return None


def looks_like_task(text, users):
    """True if `text` plausibly assigns work and deserves an AI call."""
    if not text or len(text) < MIN_LENGTH:
        return False
    if leading_name(text, users) is not None:
        return True
    return any(hint in text for hint in REQUEST_HINTS)


def looks_like_followup(text):
    """True if `text` might be reporting progress on an existing task."""
    if not text:
        return False
    return any(hint in text for hint in FOLLOWUP_HINTS)
