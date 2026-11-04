"""Offline tests for unlinking: the guided steps, the checks around them, and the buttons on the
Signal page. They use a temporary database and a fake Signal API."""

import sqlite3
import unittest

from tests.test_link import NUMBER, OTHER, PHONE, ROBOT, LinkBase
from tests.test_web import PW, setUpModule, tearDownModule  # noqa: F401


class UnlinkBase(LinkBase):
    def unlink(self, confirm="UNLINK", password=PW, token=None, headers=None):
        return self.client.post("/unlink", data={"confirm": confirm, "password": password,
                                                 "csrf": token or self.csrf()}, headers=headers or {})

    def db_status(self):
        return self.row("SELECT status FROM accounts")[0][0]

    def page(self):
        return self.client.get("/signal").text

    def events(self):
        return self.row("SELECT event_type, status FROM log_entries")

    def operations(self):
        return [r[0] for r in self.row("SELECT operation FROM audit_log")]


class Buttons(UnlinkBase):
    def test_linked_offers_unlink(self):
        self.state_linked()
        page = self.page()
        self.assertIn('action="/unlink"', page)
        self.assertIn("Type UNLINK", page)
        self.assertIn("<h2>Unlink</h2>", page)

    def test_removed_on_the_phone_offers_clean_up(self):
        self.fake.registered = [NUMBER]
        self.fake.device_lists[NUMBER] = [PHONE]
        self.assertIn("<h2>Clean up</h2>", self.page())

    def test_marked_linked_but_not_registered_offers_clean_up(self):
        self.assertIn("<h2>Clean up</h2>", self.page())

    def test_nothing_offered_when_the_api_is_down(self):
        self.fake.down = True
        self.assertNotIn('action="/unlink"', self.page())

    def test_nothing_offered_for_a_different_account(self):
        self.scan(OTHER)
        self.assertNotIn('action="/unlink"', self.page())

    def test_nothing_offered_when_already_clean(self):
        self.con.execute("UPDATE accounts SET status = 'unlinked'")
        self.con.commit()
        self.assertNotIn('action="/unlink"', self.page())

    def test_unfinished_when_the_api_still_has_the_account(self):
        self.con.execute("UPDATE accounts SET status = 'unlinked'")
        self.con.commit()
        self.state_linked()
        page = self.page()
        self.assertIn("Unlinking not finished", page)
        self.assertIn("<h2>Finish unlinking</h2>", page)

    def test_no_form_while_a_link_is_in_progress(self):
        self.start()
        page = self.page()
        self.assertIn("link-box", page)
        self.assertNotIn('action="/unlink"', page)

    def test_the_link_page_says_a_code_works_only_once(self):
        self.start()
        self.assertIn("works only once", self.page())


class Unlinking(UnlinkBase):
    def test_unlink_works(self):
        self.state_linked()
        r = self.unlink()
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/signal"))
        self.assertEqual(self.fake.calls, ["unregister", "delete"])
        self.assertEqual(self.db_status(), "unlinked")
        page = self.page()
        self.assertIn("Unlinked.", page)
        self.assertIn("Not linked", page)
        self.assertNotIn(NUMBER, page)
        self.assertIn("unlink_started", self.operations())
        self.assertIn("account_unlinked", self.operations())
        self.assertIn(("unlink_done", "ok"), self.events())
        self.assertNotIn("Unlinked.", self.page())  # the message is shown once

    def test_the_robot_is_marked_unlinked_before_the_signal_calls(self):
        self.state_linked()
        seen = []
        original = self.fake.unregister

        def spy(number):
            c = sqlite3.connect(self.db)
            try:
                seen.append(c.execute("SELECT status FROM accounts").fetchone()[0])
            finally:
                c.close()
            original(number)

        self.fake.unregister = spy
        self.unlink()
        self.assertEqual(seen, ["unlinked"])

    def test_a_failed_unregister_stops_and_can_be_finished(self):
        self.state_linked()
        self.fake.fail_at = "unregister"
        self.unlink()
        self.assertEqual(self.fake.calls, ["unregister"])
        self.assertEqual(self.db_status(), "unlinked")
        page = self.page()
        self.assertIn("did not finish", page)
        self.assertIn("stop using the account", page)
        self.assertIn("unlink_failed", self.operations())
        self.assertIn(("unlink_failed", "failed"), self.events())
        page = self.page()
        self.assertIn("<h2>Finish unlinking</h2>", page)
        self.fake.fail_at = None
        self.unlink()
        self.assertEqual(self.fake.calls, ["unregister", "unregister", "delete"])
        page = self.page()
        self.assertIn("Not linked", page)
        self.assertNotIn('action="/unlink"', page)

    def test_a_failed_delete_stops_and_can_be_finished(self):
        self.state_linked()
        self.fake.fail_at = "delete"
        self.unlink()
        self.assertEqual(self.fake.calls, ["unregister", "delete"])
        page = self.page()
        self.assertIn("local Signal data", page)
        self.assertIn("<h2>Finish unlinking</h2>", self.page())
        self.fake.fail_at = None
        self.unlink()
        self.assertEqual(self.fake.calls, ["unregister", "delete", "unregister", "delete"])
        self.assertNotIn('action="/unlink"', self.page())

    def test_the_account_still_listed_afterwards_is_reported(self):
        self.state_linked()
        self.fake.unregister = lambda number: self.fake.calls.append("unregister")  # does not remove it
        self.unlink()
        page = self.page()
        self.assertIn("did not finish", page)
        self.assertIn("account is gone", page)

    def test_clean_up_after_a_removal_on_the_phone(self):
        self.fake.accounts_fail = True  # as seen on the real API: the account list errors
        self.unlink()
        self.assertEqual(self.fake.calls, ["unregister", "delete"])
        self.assertEqual(self.db_status(), "unlinked")
        self.assertIn("Unlinked.", self.page())

    def test_wrong_confirmation_word_does_nothing(self):
        self.state_linked()
        self.unlink(confirm="yes")
        self.assertIn("Type UNLINK", self.page())
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.db_status(), "linked")
        self.assertEqual(self.row("SELECT failed_attempts FROM users")[0][0], 0)

    def test_wrong_password_is_counted(self):
        self.state_linked()
        self.unlink(password="wrong-pass-1")
        self.assertIn("password is wrong", self.page())
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.db_status(), "linked")
        self.assertEqual(self.row("SELECT failed_attempts FROM users")[0][0], 1)
        self.assertIn("unlink_password_failed", self.operations())

    def test_five_wrong_passwords_lock_everything(self):
        self.state_linked()
        for _ in range(5):
            self.unlink(password="wrong-pass-1")
        self.assertIn("ocked", self.page())
        self.unlink()  # the right password, but locked
        self.assertIn("ocked", self.page())
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.db_status(), "linked")
        self.assertIn("blocked", self.operations())
        self.assertEqual(self.login(client=self.new_client()).status_code, 429)

    def test_csrf_and_origin_are_needed(self):
        self.state_linked()
        self.assertEqual(self.unlink(token="x" * 32).status_code, 403)
        self.assertEqual(self.unlink(headers={"origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.unlink(headers={"origin": "null"}).status_code, 403)
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.db_status(), "linked")

    def test_signed_out(self):
        self.state_linked()
        r = self.new_client().post("/unlink", data={"confirm": "UNLINK", "password": PW, "csrf": "x"})
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/login"))
        self.assertEqual(self.fake.calls, [])

    def test_a_different_account_is_refused(self):
        self.scan(OTHER)
        self.unlink()
        self.assertIn("different account", self.page())
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.db_status(), "linked")

    def test_nothing_recorded_means_nothing_to_unlink(self):
        self.fresh()
        self.unlink()
        self.assertIn("nothing to unlink", self.page())
        self.assertEqual(self.fake.calls, [])

    def test_refused_while_linking_is_in_progress(self):
        self.start()
        self.unlink()
        self.assertIn("link is in progress", self.page())
        self.assertEqual(self.fake.calls, [])
        self.assertEqual(self.db_status(), "linked")

    def test_linking_again_after_unlinking(self):
        self.state_linked()
        self.unlink()
        self.assertEqual(self.db_status(), "unlinked")
        self.start()
        self.scan()
        self.assertEqual(self.check().json(), {"done": True, "ok": True})
        self.assertEqual(self.db_status(), "linked")
        self.assertEqual(len(self.accounts()), 1)

    def test_the_number_is_never_in_a_page_or_a_log(self):
        self.state_linked()
        self.fake.fail_at = "delete"
        self.unlink()
        self.assertNotIn(NUMBER, self.page())
        details = " ".join(str(r[0]) for r in self.row("SELECT detail FROM log_entries"))
        self.assertNotIn(NUMBER, details)


if __name__ == "__main__":
    unittest.main()
