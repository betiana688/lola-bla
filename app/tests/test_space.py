"""The Space builder puts one clean, installable package together."""

import importlib.util
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("build_space", ROOT / "publish" / "build_space.py")
build_space = importlib.util.module_from_spec(spec)
sys.modules["build_space"] = build_space
spec.loader.exec_module(build_space)


def fake_pollen(root):
    (root / "src" / "reachy_mini_conversation_app").mkdir(parents=True)
    (root / "src" / "reachy_mini_conversation_app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "profiles" / "default").mkdir(parents=True)
    (root / "profiles" / "default" / "profile.md").write_text("+++\n+++\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1"\ndependencies = ["openai==2.28.0", "reachy-mini>=1.10.0rc5"]\n', encoding="utf-8")
    return root


class SpaceBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.tmp_path = Path(self.tmp.name)
        self.pollen = fake_pollen(self.tmp_path / "pollen")
        self.out = self.tmp_path / "space"

    def test_layout_and_what_is_left_out(self):
        build_space.build(self.pollen, self.out)
        for name in ("pyproject.toml", "index.html", "style.css", "NOTICE", "LICENSE",
                     "src/lola_bla/main.py", "src/lola_console/templates", "src/reachy_talk_data/profiles/default/profile.md",
                     "src/lola_bla/content/tools/sleep_robot.py", "src/lola_bla/content/messaging/schema.sql"):
            self.assertTrue((self.out / name).exists(), name)
        self.assertIn("reachy_mini_python_app", (self.out / "README.md").read_text(encoding="utf-8"))
        self.assertFalse((self.out / "src/lola_bla/content/tools/test_mic_handoff.py").exists())
        profile = (self.out / "src/lola_bla/content/profiles/lola/profile.md").read_text(encoding="utf-8")
        self.assertNotIn("test_mic_handoff", profile)
        self.assertIn("sleep_robot", profile)

    def test_one_package_with_the_right_dependencies(self):
        build_space.build(self.pollen, self.out)
        project = tomllib.loads((self.out / "pyproject.toml").read_text(encoding="utf-8"))["project"]
        self.assertEqual(project["entry-points"]["reachy_mini_apps"], {"lola_bla": "lola_bla.main:LolaBla"})
        names = {build_space.req_name(d) for d in project["dependencies"]}
        self.assertTrue({"openai", "starlette", "requests", "cryptography"} <= names)
        self.assertFalse(names & {"lola-console", "reachy-mini-conversation-app"})
        self.assertIn("reachy-mini>=1.14.0", project["dependencies"])

    def test_rebuild_keeps_git_and_refuses_a_foreign_folder(self):
        build_space.build(self.pollen, self.out)
        (self.out / ".git").mkdir()
        build_space.build(self.pollen, self.out)
        self.assertTrue((self.out / ".git").is_dir())
        foreign = self.tmp_path / "other"
        foreign.mkdir()
        (foreign / "notes.txt").write_text("mine", encoding="utf-8")
        with self.assertRaises(SystemExit):
            build_space.build(self.pollen, foreign)
        self.assertTrue((foreign / "notes.txt").exists())

    def test_the_final_check_stops_a_secret_and_private_files(self):
        build_space.build(self.pollen, self.out)
        (self.out / "oops.txt").write_text("token " + "hf_" + "A" * 30, encoding="utf-8")
        with self.assertRaises(SystemExit):
            build_space.check(self.out)
        (self.out / "oops.txt").unlink()
        (self.out / "lola.db").write_bytes(b"x")
        with self.assertRaises(SystemExit):
            build_space.check(self.out)


if __name__ == "__main__":
    unittest.main()
