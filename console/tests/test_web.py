"""Offline tests for the console web app. They use a temporary database built from the real
schema and fast password hashing. Your real database is never touched."""

import os
import re
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from starlette.testclient import TestClient

from lola_console import auth, users
from lola_console.sessions import SESSION_SECONDS, Signer
from lola_console.web import MAX_FAILED, create_app

SCHEMA = Path(__file__).resolve().parents[2] / "app" / "local_data" / "schema.sql"
PW = "blue-tree-sky-9"
PW2 = "green-lake-moon-4"
SECRET = b"test-secret-key-32-bytes-long!!!"
CSRF_RE = re.compile(r'name="csrf" value="([^"]+)"')
_old_n = auth.SCRYPT_N


def setUpModule():
    auth.SCRYPT_N = 2 ** 10  # fast hashing, tests only


def tearDownModule():
    auth.SCRYPT_N = _old_n


class WebBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.chmod(self.tmp.name, 0o700)
        self.db = Path(self.tmp.name) / "test.db"
        con = sqlite3.connect(self.db)
        con.executescript(SCHEMA.read_text())
        con.execute("INSERT INTO accounts (id, signal_number, status) VALUES ('acc1', 'test-number', 'linked')")
        con.commit()
        con.close()
        self.con = users.connect(self.db)
        users.create_first_user(self.con, "betiana", PW, "pi_shell:test")
        self.client = self.new_client()

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def new_client(self, secret=SECRET, cookie=None):
        app = create_app(db_path=self.db, secret=secret, allowed_hosts=["testserver"])
        client = TestClient(app, base_url="https://testserver", follow_redirects=False)
        if cookie:
            client.cookies.set("lola_session", cookie)
        return client

    def login(self, username="betiana", password=PW, client=None, headers=None):
        client = client or self.client
        token = CSRF_RE.search(client.get("/login").text).group(1)
        return client.post("/login", data={"username": username, "password": password, "csrf": token},
                           headers=headers or {})

    def row(self, sql, args=()):
        return self.con.execute(sql, args).fetchall()

    def user_id(self):
        return self.row("SELECT id FROM users")[0][0]


class SignedOut(WebBase):
    def test_home_redirects_when_signed_out(self):
        r = self.client.get("/")
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/login"))

    def test_login_page_and_headers(self):
        r = self.client.get("/login")
        self.assertEqual(r.status_code, 200)
        self.assertIn('name="csrf"', r.text)
        self.assertIn("default-src 'none'", r.headers["content-security-policy"])
        self.assertEqual(r.headers["cache-control"], "no-store")
        self.assertEqual(r.headers["x-frame-options"], "DENY")
        self.assertEqual(r.headers["x-content-type-options"], "nosniff")
        self.assertNotIn("strict-transport-security", r.headers)

    def test_static_files(self):
        self.assertIn("javascript", self.client.get("/static/app.js").headers["content-type"])
        self.assertIn("text/css", self.client.get("/static/style.css").headers["content-type"])

    def test_bad_host_refused(self):
        self.assertEqual(self.client.get("/login", headers={"host": "evil.example"}).status_code, 400)

    def test_logout_get_not_allowed(self):
        self.assertEqual(self.client.get("/logout").status_code, 405)


class SignIn(WebBase):
    def test_wrong_password(self):
        r = self.login(password="wrong-pass-1")
        self.assertEqual(r.status_code, 401)
        self.assertIn("Wrong username or password", r.text)
        self.assertEqual(self.row("SELECT failed_attempts FROM users")[0][0], 1)
        self.assertIn(("console:anonymous", "login_failed"), self.row("SELECT accessed_by, operation FROM audit_log"))
        self.assertEqual(self.row("SELECT event_type, status FROM log_entries"), [("login_failed", "failed")])

    def test_same_page_for_wrong_username_and_wrong_password(self):
        a = self.login(password="wrong-pass-1")
        b = self.login(username="nobody", password=PW)
        self.assertEqual((a.status_code, b.status_code), (401, 401))
        norm = lambda text: CSRF_RE.sub('name="csrf" value="X"', text)
        self.assertEqual(norm(a.text), norm(b.text))

    def test_typed_username_never_stored(self):
        self.login(username="hunter2-secret-guess", password="wrong-pass-1")
        self.assertNotIn(b"hunter2-secret-guess", self.db.read_bytes())

    def test_five_failures_lock_then_unlock(self):
        for _ in range(MAX_FAILED - 1):
            self.assertEqual(self.login(password="wrong-pass-1").status_code, 401)
        r = self.login(password="wrong-pass-1")
        self.assertEqual(r.status_code, 429)
        self.assertIn("locked", r.text)
        self.assertEqual(self.login().status_code, 429)  # right password, but locked
        ops = [x[0] for x in self.row("SELECT operation FROM audit_log")]
        self.assertIn("locked", ops)
        self.assertIn("blocked", ops)
        self.assertNotIn("login_ok", ops)
        failed, locked = self.row("SELECT failed_attempts, locked_until FROM users")[0]
        self.assertEqual(failed, MAX_FAILED)
        self.assertIsNotNone(locked)
        self.con.execute("UPDATE users SET locked_until = '2000-01-01 00:00:00.000'")
        self.con.commit()
        self.assertEqual(self.login().status_code, 303)
        self.assertEqual(self.row("SELECT failed_attempts, locked_until FROM users")[0], (0, None))

    def test_one_wrong_try_after_a_lock_relocks(self):
        self.con.execute("UPDATE users SET failed_attempts = 5, locked_until = '2000-01-01 00:00:00.000'")
        self.con.commit()
        self.assertEqual(self.login(password="wrong-pass-1").status_code, 429)
        self.assertEqual(self.row("SELECT locked_until > strftime('%Y-%m-%d %H:%M:%f','now') FROM users")[0][0], 1)

    def test_success_and_cookie_flags(self):
        r = self.login()
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/"))
        cookie = next(c for c in r.headers.get_list("set-cookie") if c.startswith("lola_session=")).lower()
        for flag in ("httponly", "secure", "samesite=strict"):
            self.assertIn(flag, cookie)
        home = self.client.get("/")
        self.assertEqual(home.status_code, 200)
        self.assertIn("betiana", home.text)
        self.assertIn(("console:betiana", "login_ok"), self.row("SELECT accessed_by, operation FROM audit_log"))

    def test_cookie_has_no_secrets(self):
        self.login()
        value = self.client.cookies.get("lola_session")
        self.assertNotIn(PW, value)
        self.assertNotIn("scrypt", value)

    def test_no_user_set_up(self):
        self.con.execute("UPDATE accounts SET user_id = NULL")
        self.con.execute("DELETE FROM users")
        self.con.commit()
        self.assertEqual(self.login().status_code, 401)
        self.assertEqual(self.row("SELECT record_id FROM audit_log WHERE operation = 'login_failed'"), [(None,)])

    def test_home_hides_account_number(self):
        self.login()
        home = self.client.get("/").text
        self.assertNotIn("test-number", home)
        self.assertIn("linked", home)

    def test_login_page_redirects_when_signed_in(self):
        self.login()
        self.assertEqual(self.client.get("/login").status_code, 303)


class Forgery(WebBase):
    def test_login_without_csrf_is_refused(self):
        self.client.get("/login")
        r = self.client.post("/login", data={"username": "betiana", "password": PW})
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("lola_session=", " ".join(r.headers.get_list("set-cookie")))
        self.assertEqual(self.row("SELECT failed_attempts FROM users")[0][0], 0)

    def test_login_with_other_csrf_token_refused(self):
        self.client.get("/login")
        r = self.client.post("/login", data={"username": "betiana", "password": PW, "csrf": "x" * 32})
        self.assertEqual(r.status_code, 403)

    def test_login_without_cookie_refused(self):
        r = self.new_client().post("/login", data={"username": "betiana", "password": PW, "csrf": "abc"})
        self.assertEqual(r.status_code, 403)

    def test_origin_mismatch(self):
        r = self.login(headers={"origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("login_ok", [x[0] for x in self.row("SELECT operation FROM audit_log")])
        self.assertEqual(self.login(headers={"origin": "https://testserver"}).status_code, 303)

    def test_null_origin_refused(self):
        # what a browser sends when the form was posted from another site
        r = self.login(headers={"origin": "null"})
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("login_ok", [x[0] for x in self.row("SELECT operation FROM audit_log")])

    def test_referrer_policy_lets_the_browser_send_the_real_origin(self):
        # "no-referrer" makes browsers send "Origin: null" on form posts, which locked everyone out
        self.assertEqual(self.client.get("/login").headers["referrer-policy"], "same-origin")

    def test_logout_needs_csrf(self):
        self.login()
        self.assertEqual(self.client.post("/logout", data={}).status_code, 403)
        self.assertEqual(self.client.get("/").status_code, 200)

    def test_logout(self):
        self.login()
        token = CSRF_RE.search(self.client.get("/").text).group(1)
        r = self.client.post("/logout", data={"csrf": token})
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/login"))
        self.assertEqual(self.client.get("/").status_code, 303)
        self.assertIn(("console:betiana", "logout"), self.row("SELECT accessed_by, operation FROM audit_log"))


class Sessions(WebBase):
    def test_tampered_cookie(self):
        self.login()
        token = self.client.cookies.get("lola_session")
        tampered = token[:-2] + ("AA" if token[-2:] != "AA" else "BB")
        self.assertEqual(self.new_client(cookie=tampered).get("/").status_code, 303)

    def test_other_secret_rejects_cookie(self):
        self.login()
        token = self.client.cookies.get("lola_session")
        self.assertEqual(self.new_client(cookie=token).get("/").status_code, 200)
        self.assertEqual(self.new_client(secret=b"another-secret-key-32-bytes!!!!!", cookie=token).get("/").status_code, 303)

    def test_expired_session(self):
        signer, uid = Signer(SECRET), self.user_id()
        fresh = signer.dumps("session", {"u": uid, "iat": time.time(), "c": "x"})
        old = signer.dumps("session", {"u": uid, "iat": time.time() - SESSION_SECONDS - 10, "c": "x"})
        self.assertEqual(self.new_client(cookie=fresh).get("/").status_code, 200)
        self.assertEqual(self.new_client(cookie=old).get("/").status_code, 303)

    def test_session_ends_when_password_changes(self):
        self.login()
        self.assertEqual(self.client.get("/").status_code, 200)
        time.sleep(0.05)
        users.reset_password(self.con, PW2, "pi_shell:test")
        self.assertEqual(self.client.get("/").status_code, 303)
        self.assertEqual(self.login(password=PW2).status_code, 303)

    def test_cookie_of_the_wrong_kind_rejected(self):
        wrong = Signer(SECRET).dumps("login", {"t": "x", "iat": time.time()})
        self.assertEqual(self.new_client(cookie=wrong).get("/").status_code, 303)


if __name__ == "__main__":
    unittest.main()
