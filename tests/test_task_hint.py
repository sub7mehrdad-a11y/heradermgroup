"""Tests for the local pre-filter that decides whether a message is worth
an AI call, and who a message names as the assignee.

The two regression cases at the top ("سفارش ندادم هنوز" / "امروز ارسال
نشده پس") are taken directly from task_hint.py's own module docstring — a
real incident where these were mistakenly filed as tasks. Keeping them as
tests means a future edit to REQUEST_HINTS can't silently reintroduce it.
"""
import unittest

from src.task_hint import leading_name, looks_like_task, looks_like_followup

USERS = {"mehrdad1400": "مهرداد", "farzan1369": "فرزان"}


class TestFalsePositiveRegressions(unittest.TestCase):
    """The exact messages that were wrongly filed as tasks in production."""

    def test_status_statement_about_not_ordering_is_not_a_task(self):
        self.assertFalse(looks_like_task("سفارش ندادم هنوز", USERS))

    def test_status_statement_about_shipping_is_not_a_task(self):
        self.assertFalse(looks_like_task("امروز ارسال نشده پس", USERS))


class TestLeadingName(unittest.TestCase):
    def test_plain_username_prefix(self):
        self.assertEqual(leading_name("farzan1369 فاکتورها رو بفرست", USERS), "farzan1369")

    def test_display_name_prefix(self):
        self.assertEqual(leading_name("فرزان فردا فاکتورها رو بفرست", USERS), "farzan1369")

    def test_vocative_form_with_e_suffix(self):
        self.assertEqual(leading_name("فرزانه لطفا فاکتورها رو ثبت کن", USERS), "farzan1369")

    def test_vocative_with_jan(self):
        self.assertEqual(leading_name("فرزان جان یه کار برات دارم", USERS), "farzan1369")

    def test_leading_punctuation_and_whitespace_ignored(self):
        self.assertEqual(leading_name("  @farzan1369 چک کن", USERS), "farzan1369")

    def test_other_user_recognized_too(self):
        self.assertEqual(leading_name("مهرداد لطفا موجودی رو چک کن", USERS), "mehrdad1400")

    def test_name_appearing_mid_sentence_does_not_count(self):
        # The convention is: name must lead the sentence, not just appear in it.
        self.assertIsNone(leading_name("چیزی که فرزان گفت درست بود", USERS))

    def test_no_name_at_all(self):
        self.assertIsNone(leading_name("سفارش امروز رسید", USERS))

    def test_empty_text(self):
        self.assertIsNone(leading_name("", USERS))


class TestLooksLikeTask(unittest.TestCase):
    def test_short_message_below_min_length_is_never_a_task(self):
        self.assertFalse(looks_like_task("باشه", USERS))

    def test_name_led_message_is_a_task_candidate(self):
        self.assertTrue(looks_like_task("فرزان لطفا فاکتورهای این ماه رو ثبت کن", USERS))

    def test_imperative_hint_without_a_name_is_a_task_candidate(self):
        self.assertTrue(looks_like_task("لطفا موجودی رو امروز چک کن", USERS))

    def test_bare_shop_vocabulary_without_a_name_or_imperative_is_not(self):
        # "سفارش" / "ارسال" alone must not trigger an AI call — that's the
        # exact false-positive class this filter exists to avoid.
        self.assertFalse(looks_like_task("سفارش امروز به موقع رسید خوبه", USERS))

    def test_question_without_imperative_is_not_a_task(self):
        self.assertFalse(looks_like_task("این سفارش درسته به نظرت؟", USERS))


class TestLooksLikeFollowup(unittest.TestCase):
    def test_done_phrase_is_a_followup_candidate(self):
        self.assertTrue(looks_like_followup("تمومش کردم، همه ثبت شد"))

    def test_partial_handoff_phrase_is_a_followup_candidate(self):
        self.assertTrue(looks_like_followup("نصفه‌ش رو زدم، بقیه‌ش با تو"))

    def test_unrelated_chat_is_not_a_followup(self):
        self.assertFalse(looks_like_followup("امروز هوا خیلی خوبه"))

    def test_empty_text(self):
        self.assertFalse(looks_like_followup(""))


if __name__ == "__main__":
    unittest.main()
