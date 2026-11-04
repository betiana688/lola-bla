"""Offline tests for the Signal API client, against a tiny local HTTP server (no real Signal)."""

import json
import socket
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from lola_console.signal_api import NotRegistered, SignalApi, SignalApiError

NUMBER = "+49111222333"
PNG = b"\x89PNG\r\n\x1a\n" + b"fake-image"


class Handler(BaseHTTPRequestHandler):
    routes = {}
    seen = []

    def log_message(self, *args):
        pass

    def _answer(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else b""
        Handler.seen.append((self.command, self.path, body))
        status, ctype, payload = Handler.routes.get((self.command, self.path), (404, "text/plain", b"nope"))
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    do_GET = do_POST = do_DELETE = _answer


class ClientTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.api = SignalApi(base_url=f"http://127.0.0.1:{cls.server.server_address[1]}", timeout=5)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        Handler.routes = {}
        Handler.seen = []

    def answer(self, method, path, status=200, body=b"", ctype="application/json"):
        payload = body if isinstance(body, bytes) else json.dumps(body).encode()
        Handler.routes[(method, path)] = (status, ctype, payload)

    def test_accounts(self):
        self.answer("GET", "/v1/accounts", body=[NUMBER])
        self.assertEqual(self.api.accounts(), [NUMBER])
        self.answer("GET", "/v1/accounts", body=[])
        self.assertEqual(self.api.accounts(), [])

    def test_accounts_errors(self):
        self.answer("GET", "/v1/accounts", status=500, body=b"boom")
        with self.assertRaises(SignalApiError) as e:
            self.api.accounts()
        self.assertIn("HTTP 500", str(e.exception))
        self.answer("GET", "/v1/accounts", body=b"not json")
        with self.assertRaises(SignalApiError):
            self.api.accounts()
        self.answer("GET", "/v1/accounts", body={"a": 1})
        with self.assertRaises(SignalApiError):
            self.api.accounts()

    def test_devices(self):
        devices = [{"id": 1, "name": "", "creation_timestamp": 10, "last_seen_timestamp": 11}]
        self.answer("GET", f"/v1/devices/{NUMBER}", body=devices)
        self.assertEqual(self.api.devices(NUMBER), devices)
        self.assertEqual(Handler.seen[0][1], f"/v1/devices/{NUMBER}")

    def test_devices_with_an_unexpected_shape(self):
        self.answer("GET", f"/v1/devices/{NUMBER}", body=[{"id": "x", "name": 1}])
        with self.assertRaises(SignalApiError):
            self.api.devices(NUMBER)

    def test_not_registered_is_told_apart_from_other_errors(self):
        self.answer("GET", f"/v1/devices/{NUMBER}", status=400, body=b'{"error":"User is not registered."}')
        with self.assertRaises(NotRegistered):
            self.api.devices(NUMBER)
        self.answer("GET", f"/v1/devices/{NUMBER}", status=400, body=b'{"error":"something else"}')
        with self.assertRaises(SignalApiError) as e:
            self.api.devices(NUMBER)
        self.assertNotIsInstance(e.exception, NotRegistered)
        self.assertNotIn(NUMBER, str(e.exception))

    def test_groups_are_reduced_to_what_the_console_needs(self):
        raw = [{"id": "group.xyz", "internal_id": "abc", "name": "Family", "members": ["+49111", "uuid-1", "uuid-2"],
                "blocked": False, "admins": [], "description": "d"},
               {"id": "group.pqr", "internal_id": "def", "name": "Old", "members": [], "blocked": True}]
        self.answer("GET", f"/v1/groups/{NUMBER}", body=raw)
        self.assertEqual(self.api.groups(NUMBER), [
            {"internal_id": "abc", "name": "Family", "member_count": 3, "blocked": False},
            {"internal_id": "def", "name": "Old", "member_count": 0, "blocked": True}])

    def test_groups_with_an_unexpected_shape_or_an_unregistered_number(self):
        self.answer("GET", f"/v1/groups/{NUMBER}", body=[{"name": "no id"}])
        with self.assertRaises(SignalApiError):
            self.api.groups(NUMBER)
        self.answer("GET", f"/v1/groups/{NUMBER}", status=400, body=b'{"error":"User is not registered."}')
        with self.assertRaises(NotRegistered):
            self.api.groups(NUMBER)

    def test_read_only_mode_never_writes(self):
        ro = SignalApi(base_url=f"http://127.0.0.1:{self.server.server_address[1]}", timeout=5, readonly=True)
        for call in (lambda: ro.unregister(NUMBER), lambda: ro.delete_local_data(NUMBER), lambda: ro.qr_png("x")):
            with self.assertRaises(SignalApiError):
                call()
        self.assertEqual(Handler.seen, [])
        self.answer("GET", "/v1/accounts", body=[])
        self.assertEqual(ro.accounts(), [])

    def test_contacts_are_reduced_to_what_the_console_needs(self):
        raw = [{"number": "+49100", "uuid": "u-1", "name": "Ana", "profile_name": "A", "blocked": False},
               {"number": "+49200", "uuid": "", "name": "", "profile_name": "", "given_name": "",
                "nickname": {"given_name": "", "family_name": ""}, "blocked": False},
               {"number": "+49300", "name": "", "profile_name": "Cleo P", "blocked": True},
               {"number": "", "uuid": "u-4", "name": "No number", "blocked": False},
               {"uuid": "u-5", "name": "Also none"},
               {"number": "+49400", "name": "", "nickname": {"given_name": "Dani", "family_name": "G"}}]
        self.answer("GET", f"/v1/contacts/{NUMBER}", body=raw)
        self.assertEqual(self.api.contacts(NUMBER), [
            {"number": "+49100", "name": "Ana", "blocked": False},
            {"number": "+49200", "name": "", "blocked": False},
            {"number": "+49300", "name": "Cleo P", "blocked": True},
            {"number": "+49400", "name": "Dani G", "blocked": False}])

    def test_contacts_with_an_unexpected_shape_or_an_unregistered_number(self):
        self.answer("GET", f"/v1/contacts/{NUMBER}", body={"a": 1})
        with self.assertRaises(SignalApiError):
            self.api.contacts(NUMBER)
        self.answer("GET", f"/v1/contacts/{NUMBER}", status=400, body=b'{"error":"User is not registered."}')
        with self.assertRaises(NotRegistered):
            self.api.contacts(NUMBER)

    def test_qr(self):
        self.answer("GET", "/v1/qrcodelink?device_name=reachy-mini", body=PNG, ctype="image/png")
        self.assertEqual(self.api.qr_png("reachy-mini"), PNG)
        self.answer("GET", "/v1/qrcodelink?device_name=x", body=b"<html>no</html>", ctype="text/html")
        with self.assertRaises(SignalApiError):
            self.api.qr_png("x")

    def test_unregister_never_deletes_the_account(self):
        self.answer("POST", f"/v1/unregister/{NUMBER}", status=204)
        self.api.unregister(NUMBER)
        method, path, body = Handler.seen[0]
        self.assertEqual((method, path), ("POST", f"/v1/unregister/{NUMBER}"))
        self.assertEqual(json.loads(body), {"delete_account": False, "delete_local_data": False})

    def test_unregister_when_already_not_registered(self):
        self.answer("POST", f"/v1/unregister/{NUMBER}", status=400, body=b'{"error":"User is not registered."}')
        with self.assertRaises(NotRegistered):
            self.api.unregister(NUMBER)

    def test_delete_local_data_never_overrides(self):
        self.answer("DELETE", f"/v1/devices/{NUMBER}/local-data", status=204)
        self.api.delete_local_data(NUMBER)
        method, path, body = Handler.seen[0]
        self.assertEqual((method, path), ("DELETE", f"/v1/devices/{NUMBER}/local-data"))
        self.assertEqual(json.loads(body), {"ignore_registered": False})

    def test_unreachable(self):
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        api = SignalApi(base_url=f"http://127.0.0.1:{port}", timeout=2)
        with self.assertRaises(SignalApiError) as e:
            api.devices(NUMBER)
        self.assertIn("could not reach", str(e.exception))
        self.assertNotIn(NUMBER, str(e.exception))


if __name__ == "__main__":
    unittest.main()
