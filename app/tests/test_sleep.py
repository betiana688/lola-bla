"""The sleep tool: it only sleeps after an ask and a clear yes, never by accident."""

import asyncio
import re
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from reachy_mini_conversation_app.tools import sleep_robot as sr

ROOT = Path(__file__).resolve().parents[2]


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class SleepTool(unittest.TestCase):
    def setUp(self):
        sr.reset()
        self.clock = Clock()
        p = mock.patch.object(sr, "_now", self.clock)
        p.start()
        self.addCleanup(p.stop)
        self.addCleanup(sr.reset)
        self.calls = []
        self.deps = SimpleNamespace(go_to_sleep=lambda: self.calls.append(1) or {"status": "sleeping"})
        self.tool = sr.SleepRobot()

    def call(self, confirmed):
        return asyncio.run(self.tool(self.deps, confirmed=confirmed))

    def test_the_first_call_only_asks(self):
        for confirmed in (False, True):
            sr.reset()
            self.assertEqual(self.call(confirmed)["status"], "ask_first")
            self.assertEqual(self.calls, [])

    def test_a_confirmation_right_after_the_ask_is_refused(self):
        self.call(False)
        self.clock.t += 1.0
        self.assertEqual(self.call(True)["status"], "ask_first")
        self.assertEqual(self.calls, [])

    def test_a_clear_yes_after_a_pause_sleeps_once(self):
        self.call(False)
        self.clock.t += 6.0
        self.assertEqual(self.call(True), {"status": "sleeping"})
        self.assertEqual(self.calls, [1])
        self.assertEqual(self.call(True)["status"], "ask_first")  # asked again, not asleep twice
        self.assertEqual(self.calls, [1])

    def test_an_unanswered_ask_is_forgotten(self):
        self.call(False)
        self.clock.t += sr.MAX_WAIT_S + 1
        self.assertEqual(self.call(True)["status"], "ask_first")
        self.assertEqual(self.calls, [])

    def test_confirmed_false_never_sleeps_even_after_a_pause(self):
        self.call(False)
        self.clock.t += 10
        self.assertEqual(self.call(False)["status"], "ask_first")
        self.assertEqual(self.calls, [])

    def test_only_a_real_true_counts(self):
        self.call(False)
        self.clock.t += 10
        for odd in ("true", "yes", 1, None):
            self.assertEqual(asyncio.run(self.tool(self.deps, confirmed=odd))["status"], "ask_first")
        self.assertEqual(self.calls, [])

    def test_no_sleep_function_gives_an_error_not_a_crash(self):
        self.deps = SimpleNamespace(go_to_sleep=None)
        self.call(False)
        self.clock.t += 10
        self.assertIn("error", self.call(True))

    def test_a_failing_sleep_is_reported(self):
        def boom():
            raise RuntimeError("motor")
        self.deps = SimpleNamespace(go_to_sleep=boom)
        self.call(False)
        self.clock.t += 10
        self.assertIn("sleep failed", self.call(True)["error"])


class Profile(unittest.TestCase):
    text = (ROOT / "profiles" / "lola" / "profile.md").read_text(encoding="utf-8")

    def tools(self):
        return re.search(r"default_tools = \[(.*?)\]", self.text, re.S).group(1)

    def test_lola_uses_the_checked_sleep_and_not_the_direct_one(self):
        self.assertIn('"sleep_robot"', self.tools())
        self.assertNotIn('"go_to_sleep"', self.tools())

    def test_the_personality_says_to_ask_first(self):
        self.assertIn("## SLEEP", self.text)
        self.assertIn("confirmed false", self.text)

    def test_spanish_and_german_are_covered_for_the_request_the_question_and_the_answer(self):
        for word in ("duérmete", "vete a dormir", "schlaf jetzt", "geh schlafen", "¿quieres que me duerma?",
                     "möchtest du, dass ich schlafen gehe?", "sí", "vale", "ja", "nein", "buenas noches", "gute Nacht"):
            self.assertIn(word, self.text, word)

    def test_the_tool_description_names_all_three_languages(self):
        for word in ("duérmete", "schlaf jetzt", "go to sleep"):
            self.assertIn(word, sr.SleepRobot.description, word)

    def test_install_links_the_tool(self):
        self.assertIn("sleep_robot.py", (ROOT / "app" / "install.sh").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
