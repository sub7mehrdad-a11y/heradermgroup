import re
from datetime import datetime, timedelta, timezone

# Iran has used a fixed UTC+3:30 offset with no DST since 2022.
IRAN_TZ = timezone(timedelta(hours=3, minutes=30))

_PM_WORDS = ("عصر", "بعدازظهر", "شب")
_TIME = r'(?:ساعت\s*)?(\d{1,2})(?::(\d{2}))?\s*(صبح|ظهر|بعدازظهر|عصر|شب)?'


def now_iran():
    return datetime.now(IRAN_TZ)


def _normalize(text):
    t = text.strip()
    t = t.replace("‌", " ")  # ZWNJ so «پس‌فردا» matches the same as «پس فردا»
    t = re.sub(r'^تا\s+', '', t)  # a leading "تا" ("by/until") doesn't change the meaning
    return re.sub(r'\s+', ' ', t).strip()


def _adjust_period(hour, period):
    if period in _PM_WORDS and hour <= 11:
        return hour + 12
    return hour


def _at(base, hour, minute):
    return base.replace(hour=hour % 24, minute=minute, second=0, microsecond=0)


def parse_deadline(text, now=None):
    """Parse a Persian relative/absolute deadline phrase.

    Returns an aware datetime in IRAN_TZ, or None if the phrase wasn't
    recognized. Deliberately fails closed (returns None) rather than
    guessing, so a bad deadline never silently creates a wrong-due task.
    """
    if now is None:
        now = now_iran()
    t = _normalize(text)

    m = re.match(r'^امروز(?:\s+' + _TIME + r')?$', t)
    if m:
        if m.group(1):
            return _at(now, _adjust_period(int(m.group(1)), m.group(3)), int(m.group(2) or 0))
        return _at(now, 23, 59)

    m = re.match(r'^فردا(?:\s+' + _TIME + r')?$', t)
    if m:
        base = now + timedelta(days=1)
        h = _adjust_period(int(m.group(1)), m.group(3)) if m.group(1) else 18
        mi = int(m.group(2)) if m.group(2) else 0
        return _at(base, h, mi)

    m = re.match(r'^پس\s*فردا(?:\s+' + _TIME + r')?$', t)
    if m:
        base = now + timedelta(days=2)
        h = _adjust_period(int(m.group(1)), m.group(3)) if m.group(1) else 18
        mi = int(m.group(2)) if m.group(2) else 0
        return _at(base, h, mi)

    m = re.match(r'^(\d+)\s*روز\s*دیگر(?:\s+' + _TIME + r')?$', t)
    if m:
        days = int(m.group(1))
        base = now + timedelta(days=days)
        if m.group(2):
            return _at(base, _adjust_period(int(m.group(2)), m.group(4)), int(m.group(3) or 0))
        return base

    m = re.match(r'^(\d+)\s*ساعت\s*دیگر$', t)
    if m:
        return now + timedelta(hours=int(m.group(1)))

    m = re.match(r'^' + _TIME + r'$', t)
    if m and m.group(1):
        candidate = _at(now, _adjust_period(int(m.group(1)), m.group(3)), int(m.group(2) or 0))
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate

    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})(?:\s+(\d{1,2}):(\d{2}))?$', t)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        h = int(m.group(4)) if m.group(4) else 18
        mi = int(m.group(5)) if m.group(5) else 0
        try:
            return datetime(y, mo, d, h, mi, tzinfo=IRAN_TZ)
        except ValueError:
            return None

    return None
