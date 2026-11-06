"""Package checks that need no robot hardware."""

import os
import re
import sys
import threading
import time
import tomllib
import unittest
from pathlib import Path
from unittest import mock

from reachy_mini_conversation_app.main import ReachyMiniConversationApp

from lola_bla import main as lola_main
from lola_bla.main import LolaBla

APP = Path(__file__).resolve().parent.parent
MAIN = APP / "src" / "lola_bla" / "main.py"
DAEMON_PATTERN = r'custom_app_url\s*(?::\s*[^=]+)?\s*=\s*["\']([^"\']+)["\']'


class DaemonContract(unittest.TestCase):
    def test_exactly_one_url_literal_for_the_daemon(self):
        found = re.findall(DAEMON_PATTERN, MAIN.read_text(encoding="utf-8"))
        self.assertEqual(found, ["https://reachy-mini.local:9443/"])

    def test_no_settings_web_server(self):
        self.assertIs(LolaBla.dont_start_webserver, True)

    def test_has_the_stop_handling_the_daemon_needs(self):
        text = MAIN.read_text(encoding="utf-8")
        self.assertIn("app.wrapped_run()", text)
        self.assertIn("except KeyboardInterrupt", text)

    def test_pyproject(self):
        data = tomllib.loads((APP / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(data["project"]["name"], "lola_bla")
        self.assertEqual(data["project"]["entry-points"]["reachy_mini_apps"]["lola_bla"], "lola_bla.main:LolaBla")
        deps = " ".join(data["project"]["dependencies"])
        for name in ("reachy-mini", "reachy-mini-conversation-app", "lola-console", "requests"):
            self.assertIn(name, deps)


class Privacy(unittest.TestCase):
    def test_camera_off_ui_off_profile_lola(self):
        from reachy_mini_conversation_app.utils import parse_args

        with mock.patch.object(sys, "argv", ["lola_bla"]), mock.patch.dict(os.environ, {}):
            lola_main.prepare_environment()
            args, _ = parse_args()
            self.assertTrue(args.no_camera)
            self.assertFalse(args.ui)
            self.assertEqual(os.environ["REACHY_MINI_CUSTOM_PROFILE"], "lola")


class Lifecycle(unittest.TestCase):
    def setUp(self):
        self.stop = threading.Event()
        self.served = threading.Event()
        self.ended = threading.Event()
        self.app_ran = threading.Event()
        for p in (mock.patch.object(sys, "argv", ["lola_bla"]), mock.patch.dict(os.environ, {})):
            p.start()
            self.addCleanup(p.stop)

    def fake_serve(self, stop_event, **kwargs):
        self.served.set()
        stop_event.wait(10)
        self.ended.set()

    def run_app(self, fake_run, fake_serve=None):
        app = LolaBla.__new__(LolaBla)
        with mock.patch.object(ReachyMiniConversationApp, "run", new=fake_run), \
             mock.patch("lola_console.server.serve", new=fake_serve or self.fake_serve):
            app.run(object(), self.stop)

    def test_console_stops_with_the_app(self):
        def fake_run(app, robot, stop_event):
            self.app_ran.set()
            self.served.wait(5)
            time.sleep(0.1)

        self.run_app(fake_run)
        self.assertTrue(self.app_ran.is_set())
        self.assertTrue(self.stop.is_set())
        self.assertTrue(self.ended.is_set())

    def test_console_stops_even_if_the_app_crashes(self):
        def fake_run(app, robot, stop_event):
            self.served.wait(5)
            raise RuntimeError("boom")

        with self.assertRaises(RuntimeError):
            self.run_app(fake_run)
        self.assertTrue(self.stop.is_set())
        self.assertTrue(self.ended.is_set())

    def test_app_keeps_running_if_the_console_cannot_start(self):
        def broken_serve(stop_event, **kwargs):
            raise RuntimeError("no certificate")

        def fake_run(app, robot, stop_event):
            self.app_ran.set()
            time.sleep(0.1)

        self.run_app(fake_run, fake_serve=broken_serve)
        self.assertTrue(self.app_ran.is_set())


if __name__ == "__main__":
    unittest.main()
