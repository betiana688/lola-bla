"""The docs keep their promises: every relative link resolves, and every diagram has the brand colours."""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FILES = [ROOT / "README.md", ROOT / "app" / "README.md", ROOT / "console" / "README.md",
         *sorted((ROOT / "docs").rglob("*.md"))]
LINK = re.compile(r"(?<!\!)\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)|!\[[^\]]*\]\(([^)\s]+)\)|<img[^>]+src=\"([^\"]+)\"")


class Links(unittest.TestCase):
    def test_every_relative_link_and_image_exists(self):
        broken = []
        for f in FILES:
            text = re.sub(r"```.*?```", "", f.read_text(encoding="utf-8"), flags=re.S)
            for m in LINK.finditer(text):
                target = next(g for g in m.groups() if g)
                if re.match(r"(https?:|mailto:|#)", target):
                    continue
                path = target.split("#")[0]
                if path and not (f.parent / path).exists():
                    broken.append(f"{f.relative_to(ROOT)} -> {target}")
        self.assertEqual(broken, [])


class Diagrams(unittest.TestCase):
    def test_every_diagram_has_the_brand_colours(self):
        plain = []
        for f in FILES:
            for m in re.finditer(r"```mermaid\n(.*?)```", f.read_text(encoding="utf-8"), re.S):
                if not m.group(1).startswith('%%{init: {"theme":"base"'):
                    plain.append(str(f.relative_to(ROOT)))
        self.assertEqual(plain, [])


class Guide(unittest.TestCase):
    def test_the_guide_pages_exist_and_are_linked_from_the_docs_home(self):
        home = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
        self.assertIn("use/README.md", home)
        for name in ("get-started", "daily-use", "safe-and-private", "troubleshooting"):
            self.assertTrue((ROOT / "docs" / "use" / f"{name}.md").is_file(), name)

    def test_the_guide_does_not_hold_a_phone_number_or_a_secret(self):
        for f in (ROOT / "docs" / "use").glob("*.md"):
            text = f.read_text(encoding="utf-8")
            self.assertNotRegex(text, r"\+\d{6,}", f.name)
            self.assertNotRegex(text, r"hf_[A-Za-z0-9]{20,}", f.name)


class RepoSafety(unittest.TestCase):
    def test_there_is_a_security_policy_and_dependency_alerts(self):
        policy = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        self.assertIn("Report a vulnerability", policy)
        self.assertNotRegex(policy, r"\+\d{6,}|hf_[A-Za-z0-9]{20,}")
        updates = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
        for needle in ('package-ecosystem: "pip"', 'directory: "/console"', 'directory: "/app"'):
            self.assertIn(needle, updates)

    def test_gitignore_keeps_private_data_out(self):
        ignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
        for needle in (".env", "*.wav", "signal-data/", "recordings/"):
            self.assertIn(needle, ignore)


if __name__ == "__main__":
    unittest.main()
