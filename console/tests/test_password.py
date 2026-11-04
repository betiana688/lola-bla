"""Offline tests for the change-password page. They use a temporary database and fast hashing."""

import time

from lola_console import auth
from lola_console.web import MAX_FAILED
from tests.test_web import CSRF_RE, PW, PW2, WebBase, setUpModule, tearDownModule  # noqa: F401

PAGE = "/password"


class ChangePassword(WebBase):
    def setUp(self):
        super().setUp()
        self.login()

    def csrf(self, client=None):
        return CSRF_RE.search((client or self.client).get(PAGE).text).group(1)

    def change(self, current=PW, new=PW2, repeat=None, csrf=None, headers=None, client=None):
        client = client or self.client
        data = {"current": current, "new": new, "repeat": new if repeat is None else repeat,
                "csrf": self.csrf(client) if csrf is None else csrf}
        return client.post(PAGE, data=data, headers=headers or {})

    def stored_hash(self):
        return self.row("SELECT password_hash FROM users")[0][0]

    def operations(self):
        return [r[0] for r in self.row("SELECT operation FROM audit_log")]

    def test_signed_out_is_sent_to_sign_in(self):
        other = self.new_client()
        r = other.get(PAGE)
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/login"))
        post = other.post(PAGE, data={"current": PW, "new": PW2, "repeat": PW2, "csrf": "x"})
        self.assertEqual(post.status_code, 303)
        self.assertEqual(self.row("SELECT failed_attempts FROM users")[0][0], 0)

    def test_page_fields_and_headers(self):
        r = self.client.get(PAGE)
        self.assertEqual(r.status_code, 200)
        for needle in ('name="current"', 'name="new"', 'name="repeat"', 'name="csrf"',
                       'autocomplete="new-password"', "data-toggle-password", "5 characters"):
            self.assertIn(needle, r.text)
        self.assertEqual(r.headers["cache-control"], "no-store")

    def test_change_works_and_is_audited(self):
        r = self.change()
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/?notice=password_changed"))
        self.assertTrue(auth.verify_password(PW2, self.stored_hash()))
        self.assertIn(("console:betiana", "password_changed"),
                      self.row("SELECT accessed_by, operation FROM audit_log"))
        self.assertEqual(self.row("SELECT failed_attempts, locked_until FROM users")[0], (0, None))
        home = self.client.get(r.headers["location"])
        self.assertEqual(home.status_code, 200)
        self.assertIn("Password changed", home.text)

    def test_old_password_stops_working(self):
        self.change()
        self.assertEqual(self.login(password=PW, client=self.new_client()).status_code, 401)
        self.assertEqual(self.login(password=PW2, client=self.new_client()).status_code, 303)

    def test_current_session_survives_with_a_new_csrf_token(self):
        before_cookie, token = self.client.cookies.get("lola_session"), self.csrf()
        self.assertEqual(self.change(csrf=token).status_code, 303)
        self.assertNotEqual(self.client.cookies.get("lola_session"), before_cookie)
        self.assertEqual(self.client.get("/").status_code, 200)
        self.assertNotEqual(self.csrf(), token)

    def test_other_sessions_end(self):
        other = self.new_client()
        self.assertEqual(self.login(client=other).status_code, 303)
        self.assertEqual(other.get("/").status_code, 200)
        time.sleep(0.02)
        self.change()
        self.assertEqual(other.get("/").status_code, 303)

    def test_notice_is_only_ever_the_fixed_text(self):
        text = self.client.get("/?notice=<script>alert(1)</script>").text
        self.assertNotIn("<script>alert", text)
        self.assertNotIn("Password changed", text)

    def test_wrong_current_is_counted_and_changes_nothing(self):
        before = self.stored_hash()
        r = self.change(current="wrong-pass-1")
        self.assertEqual(r.status_code, 401)
        self.assertIn("current password is wrong", r.text)
        self.assertEqual(self.stored_hash(), before)
        self.assertEqual(self.row("SELECT failed_attempts FROM users")[0][0], 1)
        self.assertIn("password_change_failed", self.operations())
        self.assertEqual(self.row("SELECT event_type, status FROM log_entries"),
                         [("password_change_failed", "failed")])

    def test_five_wrong_lock_it(self):
        for _ in range(MAX_FAILED - 1):
            self.assertEqual(self.change(current="wrong-pass-1").status_code, 401)
        self.assertEqual(self.change(current="wrong-pass-1").status_code, 429)
        before = self.stored_hash()
        self.assertEqual(self.change().status_code, 429)  # right password, but locked
        self.assertEqual(self.stored_hash(), before)
        self.assertIn("locked", self.operations())
        self.assertEqual(self.login(client=self.new_client()).status_code, 429)  # sign-in is locked too

    def test_very_long_current_is_just_wrong(self):
        self.assertEqual(self.change(current="x" * 5000).status_code, 401)
        self.assertEqual(self.row("SELECT failed_attempts FROM users")[0][0], 1)

    def test_new_passwords_must_match(self):
        before = self.stored_hash()
        r = self.change(new=PW2, repeat="different-pass-9")
        self.assertEqual(r.status_code, 400)
        self.assertIn("do not match", r.text)
        self.assertEqual(self.stored_hash(), before)
        self.assertEqual(self.row("SELECT failed_attempts FROM users")[0][0], 0)

    def test_weak_new_password_refused(self):
        r = self.change(new="abcd")
        self.assertEqual(r.status_code, 400)
        self.assertIn("too short", r.text)
        self.assertTrue(auth.verify_password(PW, self.stored_hash()))

    def test_new_must_differ_from_current(self):
        r = self.change(new=PW)
        self.assertEqual(r.status_code, 400)
        self.assertIn("different", r.text)

    def test_username_not_allowed_inside(self):
        r = self.change(new="betiana-sky-77")
        self.assertEqual(r.status_code, 400)
        self.assertIn("username", r.text)

    def test_csrf_token_required(self):
        before = self.stored_hash()
        self.assertEqual(self.change(csrf="x" * 32).status_code, 403)
        self.assertEqual(self.change(csrf="").status_code, 403)
        self.assertEqual(self.stored_hash(), before)

    def test_origin_is_checked(self):
        before = self.stored_hash()
        for origin in ("https://evil.example", "null"):
            self.assertEqual(self.change(headers={"origin": origin}).status_code, 403)
        self.assertEqual(self.stored_hash(), before)
        self.assertEqual(self.change(headers={"origin": "https://testserver"}).status_code, 303)

    def test_passwords_never_echoed_or_stored_in_clear(self):
        r = self.change(new=PW2, repeat="different-pass-9")
        for secret in (PW, PW2, "different-pass-9"):
            self.assertNotIn(secret, r.text)
        self.change()
        self.assertNotIn(PW2.encode(), self.db.read_bytes())
