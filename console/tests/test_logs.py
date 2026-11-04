"""Offline tests for the Logs page. They use a temporary database with seeded log rows."""

import os
import re
import unittest
import uuid

from lola_console import logview
from tests.test_web import WebBase, setUpModule, tearDownModule  # noqa: F401

PHONE = "+491512345678"
UUID = "123e4567-e89b-12d3-a456-426614174000"


def berlin_available():
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo("Europe/Berlin")
        return True
    except Exception:
        return False


def entries(page):
    """Only the log entries on the page, not the filter menus (which list every event name)."""
    return "".join(re.findall(r'<article class="entry">.*?</article>', page, re.S))


class LogBase(WebBase):
    def setUp(self):
        super().setUp()
        self.old_zone = os.environ.get("LOLA_TIMEZONE")
        os.environ["LOLA_TIMEZONE"] = "UTC"
        self.login()

    def tearDown(self):
        if self.old_zone is None:
            os.environ.pop("LOLA_TIMEZONE", None)
        else:
            os.environ["LOLA_TIMEZONE"] = self.old_zone
        super().tearDown()

    def entry(self, event, status="ok", detail="", when="datetime('now')"):
        self.con.execute(f"INSERT INTO log_entries (id, message_id, occurred_at, event_type, status, detail) "
                         f"VALUES (?, NULL, {when}, ?, ?, ?)", (str(uuid.uuid4()), event, status, detail))
        self.con.commit()

    def audit_row(self, who, table, op, record, when="datetime('now')"):
        self.con.execute(f"INSERT INTO audit_log (id, accessed_by, table_name, record_id, operation, occurred_at) "
                         f"VALUES (?, ?, ?, ?, ?, {when})", (str(uuid.uuid4()), who, table, record, op))
        self.con.commit()

    def page(self, **params):
        r = self.client.get("/logs", params=params)
        self.assertEqual(r.status_code, 200)
        return r.text


class Masking(unittest.TestCase):
    def test_mask_text(self):
        text = f"to {PHONE} group {UUID} number 1234567890 id {'A' * 44} plain words stay"
        masked = logview.mask_text(text)
        for secret in (PHONE, UUID, "1234567890", "A" * 44):
            self.assertNotIn(secret, masked)
        self.assertIn("[number]", masked)
        self.assertIn("[id]", masked)
        self.assertIn("plain words stay", masked)

    def test_short_ids(self):
        self.assertEqual(logview.short("abcdefgh-1111-2222"), "abcdefgh")
        self.assertEqual(logview.short(None), "")


class Viewing(LogBase):
    def test_signed_out(self):
        r = self.new_client().get("/logs")
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/login"))

    def test_the_default_is_the_activity_log_for_the_last_seven_days(self):
        self.entry("recent_event", when="datetime('now', '-1 hours')")
        self.entry("three_days", when="datetime('now', '-3 days')")
        self.entry("ten_days", when="datetime('now', '-10 days')")
        page = self.page()
        self.assertIn("recent_event", page)
        self.assertIn("three_days", page)
        self.assertNotIn("ten_days", entries(page))
        self.assertIn("Times are in UTC", page)

    def test_periods(self):
        self.entry("recent_event", when="datetime('now', '-1 hours')")
        self.entry("three_days", when="datetime('now', '-3 days')")
        self.entry("ten_days", when="datetime('now', '-10 days')")
        day = self.page(period="1d")
        self.assertIn("recent_event", day)
        self.assertNotIn("three_days", entries(day))
        month = self.page(period="30d")
        self.assertIn("ten_days", month)
        self.assertIn("ten_days", self.page(period="all"))

    def test_highlighting(self):
        self.entry("broke", "failed", "it broke")
        self.entry("fell_back", "degraded")
        self.entry("skipped", "ignored")
        self.entry("fine", "ok")
        page = self.page()
        self.assertIn('class="badge failed">FAILED', page)
        self.assertEqual(page.count('class="badge soft"'), 2)
        self.assertIn('class="badge plain"', page)

    def test_filters(self):
        self.entry("broke", "failed")
        self.entry("fell_back", "degraded")
        self.entry("fine", "ok")
        only_failed = self.page(status="failed")
        self.assertIn("broke", only_failed)
        self.assertNotIn("fell_back", entries(only_failed))
        only_event = self.page(event="fine")
        self.assertIn("fine", only_event)
        self.assertNotIn("broke", entries(only_event))
        self.assertIn("Nothing here", self.page(status="failed", event="fine"))
        everything = self.page(status="zzz")  # not a real status: ignored
        self.assertIn("broke", everything)
        self.assertIn("fine", everything)

    def test_bad_parameters_never_break_the_page(self):
        self.entry("something")
        for params in ({"page": "abc"}, {"page": "-5"}, {"page": "99999999999999999999"}, {"view": "../etc"},
                       {"period": "bogus"}, {"status": "x'; DROP TABLE log_entries;--"}, {"event": "\x00"}):
            with self.subTest(params=params):
                self.page(**params)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM log_entries").fetchone()[0], 1)

    def test_paging_and_newest_first(self):
        for n in range(120):
            self.con.execute("INSERT INTO log_entries (id, message_id, occurred_at, event_type, status, detail) "
                             "VALUES (?, NULL, datetime('now', ?), 'bulk', 'ok', ?)",
                             (str(uuid.uuid4()), f"-{n} minutes", f"entry {n:03d}"))
        self.con.commit()
        first = self.page()
        self.assertIn("entry 000", first)
        self.assertIn("entry 049", first)
        self.assertNotIn("entry 050", first)
        self.assertLess(first.index("entry 000"), first.index("entry 001"))
        self.assertIn("page=2", first)
        self.assertNotIn("Newer", first)
        third = self.page(page="3")
        self.assertIn("entry 100", third)
        self.assertIn("entry 119", third)
        self.assertIn("Newer", third)
        self.assertNotIn("Older", third)
        beyond = self.page(page="99")
        self.assertIn("Nothing here", beyond)
        self.assertIn("Newer", beyond)

    def test_paging_keeps_the_filters(self):
        for n in range(60):
            self.con.execute("INSERT INTO log_entries (id, message_id, occurred_at, event_type, status, detail) "
                             "VALUES (?, NULL, datetime('now', ?), 'bulk', 'failed', 'x')",
                             (str(uuid.uuid4()), f"-{n} minutes"))
        self.con.commit()
        page = self.page(status="failed", period="1d")
        self.assertIn("status=failed", page)
        self.assertIn("period=1d", page)

    def test_masking_on_the_page(self):
        self.entry("leaky", "failed", f"to {PHONE} group {UUID} number 1234567890 id {'A' * 44}")
        page = self.page()
        for secret in (PHONE, UUID, "1234567890", "A" * 44):
            self.assertNotIn(secret, page)
        self.assertIn("[number]", page)
        self.assertIn("[id]", page)

    def test_html_is_escaped(self):
        self.entry("tricky", "ok", "<script>alert(1)</script>")
        page = self.page()
        self.assertNotIn("<script>alert", page)
        self.assertIn("&lt;script&gt;", page)

    def test_a_long_detail_is_cut(self):
        self.entry("long", "ok", "word " * 200)
        self.assertIn("...", self.page())

    def test_unreadable_times_are_still_listed(self):
        self.entry("odd_time", "ok", when="'garbage'")
        self.assertIn("odd_time", self.page(period="all"))

    def test_times_in_every_format_in_local_time(self):
        if not berlin_available():
            self.skipTest("no time zone data on this machine")
        os.environ["LOLA_TIMEZONE"] = "Europe/Berlin"
        for stamp in ("2026-11-04 10:00:00", "2026-11-04T10:00:00.123456+00:00", "2026-11-04T11:00:00+01:00"):
            self.entry("stamp", when=f"'{stamp}'")
        page = self.page(period="all")
        self.assertEqual(page.count("04 Nov 2026 11:00 CET"), 3)
        self.assertIn("Times are in Europe/Berlin", page)

    def test_an_unknown_zone_falls_back_to_utc(self):
        os.environ["LOLA_TIMEZONE"] = "Nowhere/None"
        self.entry("stamp", when="'2026-11-04 10:00:00'")
        page = self.page(period="all")
        self.assertIn("04 Nov 2026 10:00 UTC", page)

    def test_the_audit_view(self):
        self.audit_row("messaging_agent", "messages", "read", "abcdefgh-1111-2222-3333-444455556666")
        page = self.page(view="audit")
        for needle in ("create_user", "login_ok", "console:betiana", "messaging_agent", "abcdefgh"):
            self.assertIn(needle, page)
        self.assertNotIn("abcdefgh-1111", page)
        only = self.page(view="audit", who="console:betiana")
        self.assertIn("login_ok", only)
        self.assertNotIn("messaging_agent", entries(only))
        self.assertIn("Nothing here", self.page(view="audit", who="console:betiana", table="messages"))

    def test_viewing_changes_nothing_and_posting_is_refused(self):
        before = (self.con.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0],
                  self.con.execute("SELECT COUNT(*) FROM log_entries").fetchone()[0])
        self.page()
        self.page(view="audit")
        after = (self.con.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0],
                 self.con.execute("SELECT COUNT(*) FROM log_entries").fetchone()[0])
        self.assertEqual(before, after)
        self.assertEqual(self.client.post("/logs", data={}).status_code, 405)

    def test_the_home_page_links_here(self):
        home = self.client.get("/").text
        self.assertIn('href="/logs"', home)
        self.assertIn("status=failed", home)


if __name__ == "__main__":
    unittest.main()
