"""The landing page: plain http, answers HEAD and GET with 200, no redirect, no data.
The console link follows the address the viewer used (IP or name), opens in a new tab."""

import http.client
import os
import socket
import threading
import unittest
from unittest import mock

from lola_bla import landing


class ViewerHost(unittest.TestCase):
    def test_accepts_ip_name_and_ipv6(self):
        self.assertEqual(landing.viewer_host("192.168.178.75:9080"), "192.168.178.75")
        self.assertEqual(landing.viewer_host("reachy-mini.local:9080"), "reachy-mini.local")
        self.assertEqual(landing.viewer_host("reachy-mini.local"), "reachy-mini.local")
        self.assertEqual(landing.viewer_host("[2001:db8::1]:9080"), "[2001:db8::1]")

    def test_falls_back_for_missing_unusable_or_hostile_values(self):
        for bad in (None, "", "0.0.0.0:9080", "[::]:9080", 'evil"><script>x</script>',
                    "a b", "host/../x", "x" * 300, "[zzzz]:1", "-bad.example", "[1:2"):
            self.assertEqual(landing.viewer_host(bad), landing.FALLBACK_HOST, bad)

    def test_console_port_from_env_must_be_digits(self):
        with mock.patch.dict(os.environ, {"LOLA_CONSOLE_PORT": "9555"}):
            self.assertEqual(landing.console_url("10.0.0.5:9080"), "https://10.0.0.5:9555/")
        with mock.patch.dict(os.environ, {"LOLA_CONSOLE_PORT": '9"><x'}):
            self.assertEqual(landing.console_url("10.0.0.5:9080"), "https://10.0.0.5:9443/")


class LandingPage(unittest.TestCase):
    def start(self):
        stop, ready, evt = threading.Event(), {}, threading.Event()

        def on_ready(port):
            ready["port"] = port
            evt.set()

        t = threading.Thread(target=landing.serve, args=(stop,),
                             kwargs={"port": 0, "host": "127.0.0.1", "on_ready": on_ready}, daemon=True)
        t.start()
        self.assertTrue(evt.wait(5))
        self.addCleanup(lambda: (stop.set(), t.join(5)))
        return stop, t, ready["port"]

    def ask(self, port, method, path="/", host=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request(method, path, headers={"Host": host} if host else {})
        r = c.getresponse()
        body = r.read()
        c.close()
        return r, body

    def test_head_is_200_without_body_and_without_redirect(self):
        _, _, port = self.start()
        r, body = self.ask(port, "HEAD")
        self.assertEqual(r.status, 200)
        self.assertEqual(body, b"")
        self.assertIsNone(r.getheader("Location"))
        self.assertTrue(r.getheader("Content-Type").startswith("text/html"))

    def test_get_has_the_console_link_and_no_forms(self):
        _, _, port = self.start()
        r, body = self.ask(port, "GET", host="reachy-mini.local:9080")
        self.assertEqual(r.status, 200)
        self.assertIn(b"Lola-Bla is running", body)
        self.assertIn(b'href="https://reachy-mini.local:9443/"', body)
        self.assertNotIn(b"<form", body)
        self.assertNotIn(b"<script", body)
        self.assertIn("default-src 'none'", r.getheader("Content-Security-Policy"))

    def test_link_follows_the_address_the_viewer_used_and_opens_in_a_new_tab(self):
        _, _, port = self.start()
        _, body = self.ask(port, "GET", host="192.168.178.75:9080")
        self.assertIn(b'href="https://192.168.178.75:9443/"', body)
        self.assertIn(b'target="_blank"', body)
        self.assertIn(b'rel="noopener noreferrer"', body)
        self.assertIn(b"<b>https://192.168.178.75:9443/</b>", body)

    def test_hostile_host_header_cannot_inject_into_the_page(self):
        _, _, port = self.start()
        r, body = self.ask(port, "GET", host='evil"><script>alert(1)</script>')
        self.assertEqual(r.status, 200)
        self.assertNotIn(b"<script", body)
        self.assertNotIn(b"evil", body)
        self.assertIn(b'href="https://reachy-mini.local:9443/"', body)

    def test_stops_with_the_stop_event(self):
        stop, t, port = self.start()
        stop.set()
        t.join(5)
        self.assertFalse(t.is_alive())
        with self.assertRaises(OSError):
            socket.create_connection(("127.0.0.1", port), timeout=1)

    def test_busy_port_raises_instead_of_hanging(self):
        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        self.addCleanup(busy.close)
        with self.assertRaises(OSError):
            landing.serve(threading.Event(), port=busy.getsockname()[1], host="127.0.0.1")


if __name__ == "__main__":
    unittest.main()
