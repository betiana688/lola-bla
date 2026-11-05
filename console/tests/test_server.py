"""Offline tests for serve(): start, answer over HTTPS, stop on the event, free the port,
start again, and refuse clearly. Temporary certificate, database and port; nothing real is touched."""

import socket
import sqlite3
import ssl
import tempfile
import threading
import time
import unittest
import urllib.request
from pathlib import Path

from lola_console import server, tls, users
from tests.test_web import PW, SCHEMA, SECRET, setUpModule, tearDownModule  # noqa: F401

HOSTS = ["127.0.0.1", "localhost"]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def can_bind(port):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.tls_dir = root / "tls"
        tls.make_certificate(self.tls_dir, names=["localhost"], ips=[])
        self.db = root / "test.db"
        con = sqlite3.connect(self.db)
        con.executescript(SCHEMA.read_text())
        con.commit()
        con.close()
        self.port = free_port()
        self.running = []

    def tearDown(self):
        for stop, thread in self.running:
            stop.set()
            thread.join(10)
        self.tmp.cleanup()

    def add_user(self):
        con = users.connect(self.db)
        users.create_first_user(con, "betiana", PW, "pi_shell:test")
        con.close()

    def start(self, **extra):
        stop, errors, ready = threading.Event(), [], []

        def run():
            try:
                server.serve(stop, port=self.port, tls_dir=self.tls_dir, db_path=self.db,
                             allowed_hosts=HOSTS, secret=SECRET, on_ready=lambda: ready.append(1),
                             log_level="warning", **extra)
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        thread = threading.Thread(target=run)
        thread.start()
        self.running.append((stop, thread))
        return stop, thread, errors, ready

    def get_login(self):
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        deadline = time.time() + 8
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(f"https://127.0.0.1:{self.port}/login", context=ctx, timeout=2) as r:
                    return r.status, r.read().decode()
            except Exception:  # noqa: BLE001
                time.sleep(0.2)
        self.fail("the console never answered")


class Serving(Base):
    def test_answers_then_stops_and_frees_the_port(self):
        self.add_user()
        stop, thread, errors, ready = self.start()
        status, body = self.get_login()
        self.assertEqual(status, 200)
        self.assertIn('name="csrf"', body)
        self.assertEqual(ready, [1])
        self.assertFalse(can_bind(self.port))
        stop.set()
        thread.join(8)
        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])
        self.assertTrue(can_bind(self.port))

    def test_can_start_again_after_a_stop(self):
        self.add_user()
        for _ in range(2):
            stop, thread, errors, _ready = self.start()
            self.assertEqual(self.get_login()[0], 200)
            stop.set()
            thread.join(8)
            self.assertFalse(thread.is_alive())
            self.assertEqual(errors, [])


class Refusing(Base):
    def test_no_certificate(self):
        self.add_user()
        for f in self.tls_dir.iterdir():
            f.unlink()
        with self.assertRaisesRegex(server.ServeError, "certificate"):
            server.check_ready(self.port, self.tls_dir, self.db)

    def test_no_user(self):
        with self.assertRaisesRegex(server.ServeError, "console user"):
            server.check_ready(self.port, self.tls_dir, self.db)

    def test_busy_port(self):
        self.add_user()
        with socket.socket() as s:
            s.bind(("0.0.0.0", self.port))
            s.listen()
            with self.assertRaisesRegex(server.ServeError, "already in use"):
                server.check_ready(self.port, self.tls_dir, self.db)

    def test_serve_raises_instead_of_exiting(self):
        stop = threading.Event()
        with self.assertRaises(server.ServeError):
            server.serve(stop, port=self.port, tls_dir=self.tls_dir, db_path=self.db,
                         allowed_hosts=HOSTS, secret=SECRET)

    def test_port_comes_from_the_environment(self):
        import os
        old = os.environ.get("LOLA_CONSOLE_PORT")
        try:
            os.environ.pop("LOLA_CONSOLE_PORT", None)
            self.assertEqual(server.port_from_env(), 9443)
            os.environ["LOLA_CONSOLE_PORT"] = "9555"
            self.assertEqual(server.port_from_env(), 9555)
        finally:
            if old is None:
                os.environ.pop("LOLA_CONSOLE_PORT", None)
            else:
                os.environ["LOLA_CONSOLE_PORT"] = old


if __name__ == "__main__":
    unittest.main()
