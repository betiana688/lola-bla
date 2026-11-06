"""The landing page: plain http, answers HEAD and GET with 200, no redirect, no data.
The console link follows the address the viewer used (IP or name), opens in a new tab."""

import contextlib
import http.client
import io
import os
import re
import socket
import threading
import unittest
from unittest import mock

from lola_bla import landing


class WatchedHeaders(unittest.TestCase):
    def test_lists_only_the_watched_headers(self):
        m = http.client.HTTPMessage()
        m["Referer"] = "http://tauri.localhost/"
        m["Sec-Fetch-Dest"] = "iframe"
        m["Cookie"] = "secret=1"
        m["Authorization"] = "Bearer topsecret"
        text = landing.describe_headers(m)
        self.assertIn("Referer=http://tauri.localhost/", text)
        self.assertIn("Sec-Fetch-Dest=iframe", text)
        self.assertNotIn("secret", text)
        self.assertNotIn("Bearer", text)

    def test_values_are_cleaned_and_shortened(self):
        m = http.client.HTTPMessage()
        m["User-Agent"] = "a\tb" + "x" * 300
        text = landing.describe_headers(m)
        self.assertTrue(text.startswith("User-Agent=a?b"))
        self.assertEqual(len(text), len("User-Agent=") + 120)

    def test_says_so_when_nothing_is_watched(self):
        self.assertEqual(landing.describe_headers(http.client.HTTPMessage()), "(none of the watched headers)")


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

    def ask(self, port, method, path="/", host=None, referer=None):
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        headers = {"Host": host} if host else {}
        if referer:
            headers["Referer"] = referer
        c.request(method, path, headers=headers)
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
        self.assertIn(b"talk to abuelo", body)
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
        self.assertIn(b'class="address">https://192.168.178.75:9443/</span>', body)

    def test_a_new_robot_address_is_followed_at_once(self):
        _, _, port = self.start()
        for ip in ("192.168.178.75", "192.168.178.99", "10.1.2.3"):
            _, body = self.ask(port, "GET", host=f"{ip}:9080")
            self.assertIn(f'href="https://{ip}:9443/"'.encode(), body)

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

    def test_logs_how_the_page_was_asked_for_but_never_cookies(self):
        _, _, port = self.start()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("GET", "/", headers={"Referer": "http://tauri.localhost/", "Sec-Fetch-Dest": "iframe",
                                             "Cookie": "secret=1"})
            c.getresponse().read()
            c.close()
        text = out.getvalue()
        self.assertIn("landing page headers:", text)
        self.assertIn("Referer=http://tauri.localhost/", text)
        self.assertIn("Sec-Fetch-Dest=iframe", text)
        self.assertNotIn("secret", text)

    def test_busy_port_raises_instead_of_hanging(self):
        busy = socket.socket()
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        self.addCleanup(busy.close)
        with self.assertRaises(OSError):
            landing.serve(threading.Event(), port=busy.getsockname()[1], host="127.0.0.1")

    def test_inside_control_the_page_has_no_dead_button_but_says_where_to_click(self):
        _, _, port = self.start()
        r, body = self.ask(port, "GET", host="192.168.178.75:9080", referer="http://tauri.localhost/")
        self.assertEqual(r.status, 200)
        self.assertNotIn(b"<a ", body)
        self.assertIn(b"arrow icon", body)
        self.assertNotIn(b"9443", body)  # nothing to type, nothing that can go stale

    def test_in_a_browser_the_page_has_the_button_and_the_address(self):
        _, _, port = self.start()
        _, body = self.ask(port, "GET", host="192.168.178.75:9080")
        self.assertIn(b'class="button"', body)
        self.assertNotIn(b"arrow icon", body)
        self.assertIn(b"https://192.168.178.75:9443/", body)

    def test_unknown_referer_gets_both(self):
        _, _, port = self.start()
        _, body = self.ask(port, "GET", host="10.0.0.5:9080", referer="http://example.org/")
        self.assertIn(b'class="button"', body)
        self.assertIn(b"arrow icon", body)

    def test_the_referer_only_changes_the_display_never_redirects(self):
        _, _, port = self.start()
        for ref in (None, "http://tauri.localhost/", "http://evil.example/"):
            r, _ = self.ask(port, "HEAD", referer=ref)
            self.assertEqual(r.status, 200)
            self.assertIsNone(r.getheader("Location"))

    def test_page_has_the_description_and_no_user_info(self):
        _, _, port = self.start()
        _, body = self.ask(port, "GET")
        text = body.decode()
        self.assertIn("Lola hears and answers Signal voice messages.", text)
        self.assertNotRegex(text, r"\+\d{6,}")
        self.assertNotIn("signal</h2>", text)  # hidden while the status is unknown

    def test_brand_assets_are_served_and_nothing_else_is(self):
        _, _, port = self.start()
        r, body = self.ask(port, "GET", "/fonts/Fraunces.ttf")
        self.assertEqual((r.status, r.getheader("Content-Type")), (200, "font/ttf"))
        self.assertGreater(len(body), 10000)
        r, body = self.ask(port, "GET", "/mark.svg")
        self.assertEqual(r.getheader("Content-Type"), "image/svg+xml")
        for path in ("/fonts/../../../etc/passwd", "/fonts/other.ttf", "/etc/passwd", "/console"):
            r, body = self.ask(port, "GET", path)
            self.assertEqual(r.status, 200)
            self.assertTrue(body.startswith(b"<!doctype html>"), path)

    def test_headers_allow_only_own_fonts_and_images(self):
        _, _, port = self.start()
        r, _ = self.ask(port, "GET")
        csp = r.getheader("Content-Security-Policy")
        for part in ("default-src 'none'", "font-src 'self'", "img-src 'self'"):
            self.assertIn(part, csp)
        self.assertNotIn("script", csp)
        self.assertEqual(r.getheader("Cache-Control"), "no-store")


class SignalLine(unittest.TestCase):
    def test_shows_linked_or_not_and_hides_when_unknown(self):
        self.assertEqual(landing.signal_line(None), "")
        self.assertIn("linked</span>", landing.signal_line(True))
        self.assertIn("not linked yet", landing.signal_line(False))

    def test_the_page_shows_the_status_without_a_number(self):
        text = landing.page("10.0.0.5:9080", None, True).decode()
        self.assertIn("signal</h2>", text)
        self.assertNotRegex(text, r"\+\d{6,}")


def _luminance(hex_colour):
    h = hex_colour.lstrip("#")
    parts = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    parts = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]


def _ratio(a, b):
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


class Look(unittest.TestCase):
    def theme(self, dark):
        light = dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", landing.CSS.split("@media")[0]))
        if not dark:
            return light
        dark_block = landing.CSS.split("@media (prefers-color-scheme: dark)")[1].split("}")[0]
        return {**light, **dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})", dark_block))}

    def test_text_is_readable_in_light_and_dark(self):
        pairs = [("ink", "card"), ("ink", "page"), ("muted", "card"), ("link", "card"),
                 ("btn-text", "btn-bg"), ("header-ink", "header-bg"), ("chip-ink", "chip-bg")]
        for dark in (False, True):
            t = self.theme(dark)
            for fg, bg in pairs:
                self.assertGreaterEqual(_ratio(t[fg], t[bg]), 4.5, f"dark={dark}: {fg} on {bg}")

    def test_brand_colours_are_the_brand_colours(self):
        t = self.theme(False)
        self.assertEqual((t["banana"], t["violeta"], t["berenjena"], t["crema"]),
                         ("#F7D33E", "#7B4FC4", "#2A1640", "#FFF8E7"))

    def test_no_gradients_or_shadows_and_no_scripts(self):
        for bad in ("gradient", "shadow", "<script"):
            self.assertNotIn(bad, landing.CSS + landing.page().decode())


if __name__ == "__main__":
    unittest.main()
