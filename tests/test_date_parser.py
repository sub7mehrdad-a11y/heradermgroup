"""Tests for the Persian deadline parser.

Every case pins an explicit `now` so results are reproducible regardless of
when the suite runs — parse_deadline is fail-closed by design (returns None
rather than guessing), and that's exactly the property these tests guard.
"""
import unittest
from datetime import datetime, timedelta

from src.date_parser import parse_deadline, IRAN_TZ

# A fixed Tuesday, 10:00 — arbitrary but fixed, so "later today" / "earlier
# today" cases are unambiguous.
NOW = datetime(2026, 8, 25, 10, 0, tzinfo=IRAN_TZ)


class TestParseDeadline(unittest.TestCase):
    def test_today_without_time_defaults_to_end_of_day(self):
        result = parse_deadline("امروز", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 25, 23, 59, tzinfo=IRAN_TZ))

    def test_today_with_explicit_time(self):
        result = parse_deadline("امروز 18:00", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 25, 18, 0, tzinfo=IRAN_TZ))

    def test_tomorrow_without_time_defaults_to_6pm(self):
        result = parse_deadline("فردا", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 26, 18, 0, tzinfo=IRAN_TZ))

    def test_tomorrow_with_bare_hour(self):
        result = parse_deadline("فردا 9", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 26, 9, 0, tzinfo=IRAN_TZ))

    def test_tomorrow_evening_period_word_shifts_to_pm(self):
        # "6 عصر" must become 18:00, not stay 06:00.
        result = parse_deadline("فردا ساعت 6 عصر", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 26, 18, 0, tzinfo=IRAN_TZ))

    def test_day_after_tomorrow_with_space(self):
        result = parse_deadline("پس فردا", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 27, 18, 0, tzinfo=IRAN_TZ))

    def test_day_after_tomorrow_with_zwnj(self):
        # ZWNJ ("پس‌فردا") must normalize the same as a plain space.
        result = parse_deadline("پس‌فردا", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 27, 18, 0, tzinfo=IRAN_TZ))

    def test_numeric_days_later(self):
        result = parse_deadline("2 روز دیگر", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 27, 18, 0, tzinfo=IRAN_TZ))

    def test_spelled_out_number_days_later(self):
        result = parse_deadline("دو روز دیگه", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 27, 18, 0, tzinfo=IRAN_TZ))

    def test_persian_digits_are_understood(self):
        # date_parser.py explicitly relies on \d / int() being Unicode-aware.
        result = parse_deadline("۲ روز دیگر", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 27, 18, 0, tzinfo=IRAN_TZ))

    def test_one_week_later(self):
        result = parse_deadline("یک هفته دیگه", now=NOW)
        self.assertEqual(result, datetime(2026, 9, 1, 18, 0, tzinfo=IRAN_TZ))

    def test_hours_later_is_relative_to_now_exactly(self):
        result = parse_deadline("3 ساعت دیگر", now=NOW)
        self.assertEqual(result, NOW + timedelta(hours=3))

    def test_iso_date_with_time(self):
        result = parse_deadline("2026-08-25 14:00", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 25, 14, 0, tzinfo=IRAN_TZ))

    def test_iso_date_without_time_defaults_to_6pm(self):
        result = parse_deadline("2026-08-25", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 25, 18, 0, tzinfo=IRAN_TZ))

    def test_bare_time_later_today_stays_today(self):
        result = parse_deadline("23:00", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 25, 23, 0, tzinfo=IRAN_TZ))

    def test_bare_time_already_passed_rolls_to_tomorrow(self):
        # now is 10:00, so 09:00 has already passed today.
        result = parse_deadline("09:00", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 26, 9, 0, tzinfo=IRAN_TZ))

    def test_leading_ta_prefix_is_stripped(self):
        result = parse_deadline("تا فردا", now=NOW)
        self.assertEqual(result, datetime(2026, 8, 26, 18, 0, tzinfo=IRAN_TZ))

    def test_gibberish_returns_none_not_a_guess(self):
        self.assertIsNone(parse_deadline("قرار نیست بشه", now=NOW))

    def test_empty_string_returns_none(self):
        self.assertIsNone(parse_deadline("", now=NOW))

    def test_invalid_calendar_date_returns_none(self):
        # 2026-02-30 doesn't exist.
        self.assertIsNone(parse_deadline("2026-02-30", now=NOW))


if __name__ == "__main__":
    unittest.main()
