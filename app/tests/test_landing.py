"""The landing page: plain http, answers HEAD and GET with 200, no redirect, no data."""

import http.client
import socket
import threading
import unittest

from lola_bla import landing


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

    def ask(self, port, method, path="/"):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request(method, path)
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
        r, body = self.ask(port, "GET")
        self.assertEqual(r.status, 200)
        self.assertIn(b"Lola-Bla is running", body)
        self.assertIn(b"https://reachy-mini.local:9443/", body)
        self.assertNotIn(b"<form", body)
        self.assertIn("default-src 'none'", r.getheader("Content-Security-Policy"))

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
