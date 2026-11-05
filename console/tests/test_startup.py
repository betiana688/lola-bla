"""Offline tests for the start-at-wake-up switch: the robot-service client, the state logic and the
console route, against a stand-in robot service on a temporary port. The real one is never touched."""

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from starlette.testclient import TestClient

from lola_console import daemon_api, startup
from lola_console.daemon_api import APP_NAME, DaemonClient, DaemonError
from lola_console.web import MAX_FAILED, create_app
from tests.test_web import CSRF_RE, PW, SECRET, WebBase, setUpModule, tearDownModule  # noqa: F401

NOBODY = "http://127.0.0.1:1"


class StubDaemon:
    def __init__(self, installed=(), startup_app=None, keep_changes=True):
        self.installed, self.startup, self.keep, self.puts = list(installed), startup_app, keep_changes, []
        stub = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, code, payload):
                body = json.dumps(payload).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                if self.path == "/api/apps/list-available/installed":
                    self._send(200, [{"name": n, "source_kind": "installed", "description": "", "url": None,
                                      "extra": {}} for n in stub.installed])
                elif self.path == "/api/apps/startup-app":
                    self._send(200, {"startup_app": stub.startup})
                else:
                    self._send(404, {})

            def do_PUT(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                stub.puts.append(body)
                value = body.get("startup_app")
                if value is not None and value not in stub.installed:
                    self._send(422, {"detail": "not installed"})
                    return
                if stub.keep:
                    stub.startup = value
                self._send(200, {"startup_app": stub.startup})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def client(self):
        return DaemonClient(f"http://127.0.0.1:{self.server.server_address[1]}", timeout=2)

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class Client(unittest.TestCase):
    def test_the_address_is_the_robot_itself_and_cannot_be_configured(self):
        self.assertEqual(DaemonClient().base, "http://127.0.0.1:8000")
        self.assertNotIn("environ", Path(daemon_api.__file__).read_text())

    def test_reads_and_writes(self):
        stub = StubDaemon([APP_NAME, "other"], None)
        try:
            c = stub.client()
            self.assertEqual(c.installed_names(), [APP_NAME, "other"])
            self.assertIsNone(c.startup_app())
            c.set_startup_app(APP_NAME)
            self.assertEqual(c.startup_app(), APP_NAME)
            c.set_startup_app(None)
            self.assertIsNone(c.startup_app())
            self.assertEqual(stub.puts, [{"startup_app": APP_NAME}, {"startup_app": None}])
        finally:
            stub.close()

    def test_unreachable(self):
        with self.assertRaises(DaemonError):
            DaemonClient(NOBODY, timeout=1).startup_app()

    def test_a_refusal_carries_its_status(self):
        stub = StubDaemon([], None)
        try:
            with self.assertRaises(DaemonError) as caught:
                stub.client().set_startup_app("nothing")
            self.assertEqual(caught.exception.status, 422)
        finally:
            stub.close()


class Logic(unittest.TestCase):
    def run_case(self, installed, current, action, keep=True):
        stub = StubDaemon(installed, current, keep)
        try:
            result = startup.change(stub.client(), action)
            return result, stub.puts, stub.startup
        finally:
            stub.close()

    def state(self, installed, current):
        stub = StubDaemon(installed, current)
        try:
            return startup.get_state(stub.client())
        finally:
            stub.close()

    def test_states(self):
        self.assertEqual(self.state([], None)["state"], "not_installed")
        self.assertEqual(self.state([APP_NAME], None)["state"], "off")
        self.assertEqual(self.state([APP_NAME], APP_NAME)["state"], "on")
        other = self.state([APP_NAME, "x"], "x")
        self.assertEqual((other["state"], other["other"]), ("other", "x"))
        self.assertEqual(startup.get_state(DaemonClient(NOBODY, timeout=1))["state"], "unavailable")

    def test_turn_on_and_off_send_exactly_one_call(self):
        r, puts, now = self.run_case([APP_NAME], None, "on")
        self.assertEqual((r["changed"], r["notice"], r["audit"], puts, now),
                         (True, "startup_on", "startup_on", [{"startup_app": APP_NAME}], APP_NAME))
        r, puts, now = self.run_case([APP_NAME], APP_NAME, "off")
        self.assertEqual((r["changed"], r["notice"], puts, now), (True, "startup_off", [{"startup_app": None}], None))

    def test_not_installed_sends_nothing(self):
        r, puts, _ = self.run_case([], None, "on")
        self.assertEqual((r["changed"], r["notice"], puts), (False, "startup_not_installed", []))

    def test_never_clears_another_apps_setting(self):
        r, puts, now = self.run_case([APP_NAME, "x"], "x", "off")
        self.assertEqual((r["changed"], r["notice"], puts, now), (False, "startup_already_off", [], "x"))

    def test_turning_on_replaces_another_app(self):
        r, puts, now = self.run_case([APP_NAME, "x"], "x", "on")
        self.assertEqual((r["changed"], now), (True, APP_NAME))

    def test_already_in_place(self):
        self.assertEqual(self.run_case([APP_NAME], APP_NAME, "on")[0]["notice"], "startup_already_on")
        self.assertEqual(self.run_case([APP_NAME], None, "off")[0]["notice"], "startup_already_off")

    def test_odd_action_does_nothing(self):
        r, puts, _ = self.run_case([APP_NAME], None, "sideways")
        self.assertEqual((r["changed"], r["notice"], puts), (False, "startup_nothing", []))

    def test_a_change_the_service_does_not_keep_is_a_failure(self):
        r, puts, _ = self.run_case([APP_NAME], None, "on", keep=False)
        self.assertEqual((r["changed"], r["notice"], bool(r["error"])), (False, "startup_failed", True))

    def test_unreachable_changes_nothing(self):
        r = startup.change(DaemonClient(NOBODY, timeout=1), "on")
        self.assertEqual((r["changed"], r["notice"], bool(r["error"])), (False, "startup_unreachable", True))


class Switch(WebBase):
    installed = (APP_NAME,)
    current = None

    def setUp(self):
        self.stub = StubDaemon(self.installed, self.current)
        self.daemon = self.stub.client()
        super().setUp()
        self.login()

    def tearDown(self):
        super().tearDown()
        self.stub.close()

    def new_client(self, secret=SECRET, cookie=None):
        app = create_app(db_path=self.db, secret=secret, allowed_hosts=["testserver"], daemon_client=self.daemon)
        client = TestClient(app, base_url="https://testserver", follow_redirects=False)
        if cookie:
            client.cookies.set("lola_session", cookie)
        return client

    def token(self):
        return CSRF_RE.search(self.client.get("/").text).group(1)

    def post(self, action, password=PW, **kw):
        return self.client.post("/startup", data={"action": action, "csrf": self.token(), "password": password}, **kw)

    def audit_ops(self):
        return [r[0] for r in self.row("SELECT operation FROM audit_log")]


class WhenOff(Switch):
    def test_home_offers_turn_on(self):
        html = self.client.get("/").text
        self.assertIn("danger zone", html)
        self.assertIn('name="action" value="on"', html)
        self.assertNotIn('name="action" value="off"', html)

    def test_turn_on_changes_the_robot_and_is_audited(self):
        r = self.post("on")
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/?notice=startup_on"))
        self.assertEqual((self.stub.startup, self.stub.puts), (APP_NAME, [{"startup_app": APP_NAME}]))
        self.assertIn("startup_on", self.audit_ops())
        self.assertIn("wakes up", self.client.get("/?notice=startup_on").text)

    def test_missing_csrf_changes_nothing(self):
        r = self.client.post("/startup", data={"action": "on"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.stub.puts, [])

    def test_wrong_origin_changes_nothing(self):
        r = self.post("on", headers={"Origin": "https://evil.example"})
        self.assertEqual(r.status_code, 403)
        self.assertEqual(self.stub.puts, [])

    def test_signed_out_changes_nothing(self):
        r = self.new_client().post("/startup", data={"action": "on", "csrf": "x"})
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/login"))
        self.assertEqual(self.stub.puts, [])

    def test_odd_action(self):
        r = self.post("sideways")
        self.assertEqual(r.headers["location"], "/?notice=startup_nothing")
        self.assertEqual(self.stub.puts, [])


class WhenOn(Switch):
    current = APP_NAME

    def test_home_offers_turn_off_and_it_works(self):
        html = self.client.get("/").text
        self.assertIn('name="action" value="off"', html)
        self.assertNotIn('name="action" value="on"', html)
        r = self.post("off")
        self.assertEqual(r.headers["location"], "/?notice=startup_off")
        self.assertEqual((self.stub.startup, self.stub.puts), (None, [{"startup_app": None}]))
        self.assertIn("startup_off", self.audit_ops())


class WhenAnotherAppOwnsIt(Switch):
    installed = (APP_NAME, "other_app")
    current = "other_app"

    def test_it_says_so_and_never_clears_it(self):
        html = self.client.get("/").text
        self.assertIn("other_app", html)
        self.assertNotIn('name="action" value="off"', html)
        r = self.post("off")
        self.assertEqual(r.headers["location"], "/?notice=startup_already_off")
        self.assertEqual((self.stub.startup, self.stub.puts), ("other_app", []))

    def test_turning_on_replaces_it(self):
        self.assertIn("replaces", self.client.get("/").text)
        self.post("on")
        self.assertEqual(self.stub.startup, APP_NAME)


class WhenNotInstalled(Switch):
    installed = ()

    def test_no_buttons_and_nothing_sent(self):
        html = self.client.get("/").text
        self.assertIn("not installed", html)
        self.assertNotIn('name="action"', html)
        r = self.post("on")
        self.assertEqual(r.headers["location"], "/?notice=startup_not_installed")
        self.assertEqual(self.stub.puts, [])


class WhenTheRobotServiceIsDown(WebBase):
    def new_client(self, secret=SECRET, cookie=None):
        app = create_app(db_path=self.db, secret=secret, allowed_hosts=["testserver"],
                         daemon_client=DaemonClient(NOBODY, timeout=1))
        client = TestClient(app, base_url="https://testserver", follow_redirects=False)
        if cookie:
            client.cookies.set("lola_session", cookie)
        return client

    def test_home_still_works_and_says_so(self):
        self.login()
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("robot service", r.text)
        self.assertNotIn('name="action"', r.text)

    def test_a_change_is_reported_and_logged(self):
        self.login()
        token = CSRF_RE.search(self.client.get("/").text).group(1)
        r = self.client.post("/startup", data={"action": "on", "csrf": token, "password": PW})
        self.assertEqual(r.headers["location"], "/?notice=startup_unreachable")
        self.assertTrue(self.row("SELECT 1 FROM log_entries WHERE event_type = 'startup_error'"))
        self.assertFalse(self.row("SELECT 1 FROM audit_log WHERE operation LIKE 'startup_%'"))


class Password(Switch):
    def test_wrong_password_changes_nothing(self):
        r = self.post("on", password="not-the-password")
        self.assertEqual(r.headers["location"], "/?notice=startup_wrong_password")
        self.assertEqual(self.stub.puts, [])
        self.assertTrue(any("password_failed" in op for op in self.audit_ops()))

    def test_no_password_changes_nothing(self):
        r = self.client.post("/startup", data={"action": "on", "csrf": self.token()})
        self.assertEqual(r.headers["location"], "/?notice=startup_wrong_password")
        self.assertEqual(self.stub.puts, [])

    def test_the_home_page_asks_for_the_password(self):
        self.assertIn('name="password"', self.client.get("/").text.split("danger zone")[1])

    def test_too_many_wrong_passwords_lock_it_even_for_the_right_one(self):
        for _ in range(MAX_FAILED):
            r = self.post("on", password="wrong-one")
        self.assertEqual(r.headers["location"], "/?notice=startup_locked")
        r = self.post("on")
        self.assertEqual(r.headers["location"], "/?notice=startup_locked")
        self.assertEqual(self.stub.puts, [])


if __name__ == "__main__":
    unittest.main()
