"""Cheap local pre-filter deciding whether a message is worth an AI call.

Without this, every casual line of group chat ("اسنس کوزارکس چی؟") burns a
Gemini request. The two of them chat constantly, so that drained the free
tier for no benefit. A message only reaches the model if it carries at
least one hint of being an assignment.
"""

TIME_HINTS = (
    "فردا", "امروز", "پس فردا", "پس‌فردا", "امشب", "صبح", "ظهر", "عصر", "شب",
    "ساعت", "هفته", "ماه", "ددلاین", "مهلت", "سررسید", "تا آخر", "روز دیگ",
    "ساعت دیگ", "شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "سه شنبه",
    "چهارشنبه", "پنج‌شنبه", "پنجشنبه", "جمعه",
)

REQUEST_HINTS = (
    "لطفا", "لطفاً", "باید", "بزن", "بفرست", "برو", "بگیر", "چک کن", "پیگیری",
    "آماده کن", "اماده کن", "انجام بده", "یادت نره", "فراموش نکن", "ثبت",
    "تماس", "هماهنگ", "سفارش", "بررسی کن", "درست کن", "اضافه کن", "به‌روز",
)

MIN_LENGTH = 12


def looks_like_task(text, users):
    """True if `text` plausibly assigns work and deserves an AI call."""
    if not text or len(text) < MIN_LENGTH:
        return False

    lowered = text.lower()

    for username, display_name in users.items():
        if username in lowered or f"@{username}" in lowered:
            return True
        # Persian vocative often appends a letter ("فرزان" -> "فرزانه"),
        # so match on the name as a prefix rather than a whole word.
        if display_name and display_name in text:
            return True

    if any(hint in text for hint in TIME_HINTS):
        return True
    if any(hint in text for hint in REQUEST_HINTS):
        return True

    return False
