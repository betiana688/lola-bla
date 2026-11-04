"""Offline tests for the Signal page: status, linking, and the checks around it.
They use a temporary database and a fake Signal API; nothing real is contacted."""

import unittest

from starlette.testclient import TestClient

from lola_console import link
from lola_console.signal_api import NotRegistered, SignalApiError
from lola_console.web import create_app
from tests.test_web import CSRF_RE, SECRET, WebBase, setUpModule, tearDownModule  # noqa: F401

NUMBER = "+49111222333"
OTHER = "+49999888777"
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image"
PHONE = {"id": 1, "name": "", "creation_timestamp": 10}
ROBOT = {"id": 2, "name": "reachy-mini", "creation_timestamp": 1000}


class FakeSignal:
    """Stands in for the Signal API."""

    def __init__(self):
        self.registered = []
        self.device_lists = {}
        self.png = PNG
        self.down = False
        self.accounts_fail = False
        self.qr_requests = 0
        self.calls = []
        self.fail_at = None
        self.not_registered_at = set()
        self.group_list = []

    def accounts(self):
        if self.down or self.accounts_fail:
            raise SignalApiError("fake: no answer")
        return list(self.registered)

    def devices(self, number):
        if self.down:
            raise SignalApiError("fake: no answer")
        if number not in self.registered:
            raise NotRegistered("not registered")
        return list(self.device_lists.get(number, []))

    def qr_png(self, device_name):
        self.qr_requests += 1
        if self.down:
            raise SignalApiError("fake: no answer")
        if self.png is None:
            raise SignalApiError("the Signal API did not return a QR code image")
        return self.png

    def unregister(self, number):
        self.calls.append("unregister")
        if number not in self.registered or "unregister" in self.not_registered_at:
            raise NotRegistered("not registered")
        if self.fail_at == "unregister":
            raise SignalApiError("the Signal API answered HTTP 500")
        self.registered = [n for n in self.registered if n != number]

    def delete_local_data(self, number):
        self.calls.append("delete")
        if "delete" in self.not_registered_at:
            raise NotRegistered("not registered")
        if self.fail_at == "delete":
            raise SignalApiError("the Signal API answered HTTP 500")

    def groups(self, number):
        if self.down:
            raise SignalApiError("fake: no answer")
        if number not in self.registered:
            raise NotRegistered("not registered")
        return list(self.group_list)


class LinkBase(WebBase):
    def setUp(self):
        self.fake = FakeSignal()
        super().setUp()
        self.con.execute("UPDATE accounts SET signal_number = ?, device_id = 2, device_created_at = '1000'", (NUMBER,))
        self.con.commit()
        self.login()

    def new_client(self, secret=SECRET, cookie=None):
        app = create_app(db_path=self.db, secret=secret, allowed_hosts=["testserver"],
                         signal_client=self.fake, device_name="reachy-mini")
        client = TestClient(app, base_url="https://testserver", follow_redirects=False)
        if cookie:
            client.cookies.set("lola_session", cookie)
        return client

    def csrf(self):
        return CSRF_RE.search(self.client.get("/").text).group(1)

    def state_linked(self):
        self.fake.registered = [NUMBER]
        self.fake.device_lists[NUMBER] = [PHONE, ROBOT]

    def fresh(self):
        """A fresh install: the user exists, but no Signal account is recorded yet."""
        self.con.execute("DELETE FROM accounts")
        self.con.commit()
        self.fake.registered = []

    def scan(self, number=NUMBER, devices=None):
        """Pretend the person scanned the code."""
        self.fake.registered = [number]
        self.fake.device_lists[number] = devices if devices is not None else [PHONE, ROBOT]

    def start(self, headers=None, token=None):
        return self.client.post("/link/start", data={"csrf": token or self.csrf()}, headers=headers or {})

    def check(self):
        return self.client.post("/link/check", data={"csrf": self.csrf()})

    def operations(self):
        return [r[0] for r in self.row("SELECT operation FROM audit_log")]

    def accounts(self):
        return self.row("SELECT signal_number, status, device_id, device_created_at, user_id FROM accounts")


class Masking(unittest.TestCase):
    def test_mask(self):
        self.assertEqual(link.mask_number(NUMBER), "+49" + "\u2022" * 7 + "33")
        self.assertEqual(link.mask_number("123"), "\u2022" * 3)
        self.assertIsNone(link.mask_number(None))


class Status(LinkBase):
    def test_signed_out(self):
        other = self.new_client()
        for path in ("/signal", "/link/qr.png"):
            r = other.get(path)
            self.assertEqual((r.status_code, r.headers["location"]), (303, "/login"), path)
        self.assertEqual(other.post("/link/start", data={"csrf": "x"}).status_code, 303)
        self.assertEqual(other.post("/link/cancel", data={"csrf": "x"}).status_code, 303)
        self.assertEqual(other.post("/link/check", data={"csrf": "x"}).status_code, 401)
        self.assertEqual(self.fake.qr_requests, 0)

    def test_linked(self):
        self.state_linked()
        page = self.client.get("/signal")
        self.assertEqual(page.status_code, 200)
        self.assertIn("Linked", page.text)
        self.assertNotIn("Not linked", page.text)
        self.assertIn("+49", page.text)
        self.assertNotIn(NUMBER, page.text)
        self.assertNotIn("Start linking", page.text)

    def test_not_linked_offers_linking(self):
        page = self.client.get("/signal").text
        self.assertIn("Not linked", page)
        self.assertIn("Start linking", page)

    def test_api_down(self):
        self.fake.down = True
        page = self.client.get("/signal").text
        self.assertIn("Cannot tell", page)
        self.assertNotIn("Start linking", page)

    def test_a_different_account(self):
        self.scan(OTHER)
        page = self.client.get("/signal").text
        self.assertIn("A different account", page)
        self.assertNotIn("Start linking", page)
        self.assertNotIn(OTHER, page)

    def test_device_removed(self):
        self.fake.registered = [NUMBER]
        self.fake.device_lists[NUMBER] = [PHONE]
        page = self.client.get("/signal").text
        self.assertIn("Removed from Signal", page)
        self.assertNotIn("Start linking", page)

    def test_removed_on_the_phone_as_seen_on_the_real_api(self):
        self.fake.accounts_fail = True  # the account list errors, the number says "not registered"
        page = self.client.get("/signal").text
        self.assertIn("Not linked", page)
        self.assertNotIn("Start linking", page)

    def test_reading_the_page_changes_nothing(self):
        self.state_linked()
        snap = lambda: (self.row("SELECT * FROM accounts"), self.row("SELECT COUNT(*) FROM audit_log"),
                        self.row("SELECT COUNT(*) FROM log_entries"))
        before = snap()
        self.client.get("/signal")
        self.assertEqual(snap(), before)

    def test_policy_allows_the_page_to_check_itself(self):
        self.assertIn("connect-src 'self'", self.client.get("/signal").headers["content-security-policy"])


class Linking(LinkBase):
    def test_start_shows_the_code(self):
        self.fresh()
        r = self.start()
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/signal"))
        self.assertEqual(self.fake.qr_requests, 1)
        page = self.client.get("/signal").text
        self.assertIn('src="/link/qr.png"', page)
        self.assertIn("link-box", page)
        self.assertIn("link_started", self.operations())
        qr = self.client.get("/link/qr.png")
        self.assertEqual((qr.status_code, qr.content, qr.headers["content-type"]), (200, PNG, "image/png"))
        self.assertEqual(qr.headers["cache-control"], "no-store")

    def test_no_code_when_not_linking(self):
        self.assertEqual(self.client.get("/link/qr.png").status_code, 404)

    def test_starting_twice_asks_once(self):
        self.fresh()
        self.start()
        self.start()
        self.assertEqual(self.fake.qr_requests, 1)

    def test_refused_when_the_api_already_has_an_account(self):
        self.state_linked()
        self.assertEqual(self.start().status_code, 303)
        self.assertEqual(self.fake.qr_requests, 0)
        page = self.client.get("/signal").text
        self.assertIn("Linking is not possible", page)
        self.assertNotIn("link-box", page)

    def test_refused_when_the_api_is_down(self):
        self.fresh()
        self.fake.down = True
        self.start()
        self.assertEqual(self.fake.qr_requests, 0)
        self.assertIn("Linking is not possible", self.client.get("/signal").text)

    def test_bad_code_from_the_api(self):
        self.fresh()
        self.fake.png = None
        self.start()
        page = self.client.get("/signal").text
        self.assertIn("QR code", page)
        self.assertNotIn("link-box", page)

    def test_csrf_and_origin_are_needed(self):
        self.fresh()
        self.assertEqual(self.start(token="x" * 32).status_code, 403)
        self.assertEqual(self.start(headers={"origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.start(headers={"origin": "null"}).status_code, 403)
        self.assertEqual(self.fake.qr_requests, 0)
        self.assertEqual(self.client.post("/link/check", data={"csrf": "x" * 32}).status_code, 403)

    def test_waiting_until_the_scan_happens(self):
        self.fresh()
        self.start()
        r = self.check()
        self.assertEqual((r.status_code, r.json()), (200, {"done": False}))
        self.assertTrue(r.headers["content-type"].startswith("application/json"))
        self.scan(NUMBER, [PHONE])  # registered, but the robot's device is not there yet
        self.assertEqual(self.check().json(), {"done": False})
        self.fake.down = True  # the API may be busy right after the scan
        self.assertEqual(self.check().json(), {"done": False})

    def test_linking_a_fresh_install(self):
        self.fresh()
        self.start()
        self.scan()
        r = self.check()
        self.assertEqual(r.json(), {"done": True, "ok": True})
        self.assertEqual(self.accounts(), [(NUMBER, "linked", 2, "1000", self.user_id())])
        self.assertIn("account_linked", self.operations())
        self.assertIn(("account_linked", "ok"), self.row("SELECT event_type, status FROM log_entries"))
        self.assertEqual(self.client.get("/link/qr.png").status_code, 404)
        page = self.client.get("/signal").text
        self.assertIn("Linked", page)
        self.assertNotIn(NUMBER, page + r.text)

    def test_relinking_an_existing_account_row(self):
        self.con.execute("UPDATE accounts SET status = 'unlinked', device_id = NULL, device_created_at = NULL")
        self.con.commit()
        self.start()
        self.scan()
        self.assertEqual(self.check().json(), {"done": True, "ok": True})
        self.assertEqual(self.accounts(), [(NUMBER, "linked", 2, "1000", self.user_id())])

    def test_a_different_account_is_refused(self):
        self.start()
        before = self.accounts()
        self.scan(OTHER)
        self.assertEqual(self.check().json(), {"done": True, "ok": False})
        self.assertEqual(self.accounts(), before)
        self.assertIn("link_refused", self.operations())
        page = self.client.get("/signal").text
        self.assertIn("different Signal account", page)
        self.assertNotIn(OTHER, page)
        self.assertEqual(self.client.get("/link/qr.png").status_code, 404)

    def test_two_robot_devices_are_refused(self):
        self.start()
        before = self.accounts()
        self.scan(NUMBER, [PHONE, ROBOT, dict(ROBOT, id=3)])
        self.assertEqual(self.check().json(), {"done": True, "ok": False})
        self.assertEqual(self.accounts(), before)

    def test_the_code_expires(self):
        self.fresh()
        self.start()
        self.client.app.state.link["started"] -= 700
        self.assertEqual(self.check().json(), {"done": True, "expired": True})
        self.assertIn("expired", self.client.get("/signal").text)
        self.assertEqual(self.client.get("/link/qr.png").status_code, 404)

    def test_cancel(self):
        self.fresh()
        self.start()
        r = self.client.post("/link/cancel", data={"csrf": self.csrf()})
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/signal"))
        self.assertNotIn("link-box", self.client.get("/signal").text)
        self.assertIn("link_cancelled", self.operations())
        self.assertEqual(self.client.get("/link/qr.png").status_code, 404)


if __name__ == "__main__":
    unittest.main()
