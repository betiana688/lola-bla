"""Offline tests for the console's look: contrast, brand rules, and that the brand files match docs/brand."""

import re
import unittest
from pathlib import Path

CONSOLE = Path(__file__).resolve().parents[1]
STATIC = CONSOLE / "lola_console" / "static"
BRAND = CONSOLE.parent / "docs" / "brand"
CSS = (STATIC / "style.css").read_text()


def block(text, start):
    i = text.index(start)
    j = text.index("{", i)
    depth, k = 1, j + 1
    while depth:
        depth += {"{": 1, "}": -1}.get(text[k], 0)
        k += 1
    return text[j + 1:k - 1]


def variables(body):
    return dict(re.findall(r"--([\w-]+):\s*(#[0-9A-Fa-f]{6})\s*;", body))


def luminance(hex_colour):
    h = hex_colour.lstrip("#")
    parts = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    parts = [c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4 for c in parts]
    return 0.2126 * parts[0] + 0.7152 * parts[1] + 0.0722 * parts[2]


def ratio(a, b):
    hi, lo = sorted((luminance(a), luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


LIGHT = variables(block(CSS, ":root"))
DARK = {**LIGHT, **variables(block(CSS, "@media (prefers-color-scheme: dark)"))}
PAIRS = [("ink", "card"), ("ink", "page"), ("ink", "field"), ("muted", "card"), ("link", "card"),
         ("error", "card"), ("on-error", "error"), ("btn-text", "btn-bg"), ("header-ink", "header-bg"),
         ("notice-ink", "notice-bg"), ("focus-ink", "focus-bg"), ("ink", "banana"), ("berenjena", "banana")]


class Contrast(unittest.TestCase):
    def check(self, theme, name):
        for fg, bg in PAIRS:
            if fg == "ink" and bg == "banana":
                fg, bg = "berenjena", "banana"
            r = ratio(theme[fg], theme[bg])
            self.assertGreaterEqual(r, 4.5, f"{name}: {fg} on {bg} is only {r:.2f}")

    def test_light(self):
        self.check(LIGHT, "light")

    def test_dark(self):
        self.check(DARK, "dark")

    def test_the_brand_colours_are_the_brand_colours(self):
        self.assertEqual(
            [LIGHT[k].upper() for k in ("banana", "lila", "violeta", "berenjena", "crema")],
            ["#F7D33E", "#C9B3F2", "#7B4FC4", "#2A1640", "#FFF8E7"])


class BrandRules(unittest.TestCase):
    def test_nothing_the_brand_forbids_and_nothing_external(self):
        for word in ("gradient", "box-shadow", "text-shadow", "@import", "http:", "https:"):
            self.assertNotIn(word, CSS)
        for url in re.findall(r"url\(([^)]*)\)", CSS):
            self.assertTrue(url.strip("\"'").startswith("/static/"), url)

    def test_line_and_radius(self):
        self.assertRegex(CSS, r"--line:\s*5px")
        self.assertRegex(CSS, r"--rule:\s*3px")
        self.assertRegex(CSS, r"--radius:\s*32px")


class Files(unittest.TestCase):
    def test_brand_files_match_docs_brand(self):
        pairs = [(STATIC / "fonts" / f.name, f) for f in (BRAND / "fonts").glob("*")]
        pairs += [(STATIC / n, BRAND / n) for n in ("lola-bla-mark.svg", "lola-bla-icon.svg")]
        self.assertGreaterEqual(len(pairs), 8)
        for ours, theirs in pairs:
            self.assertTrue(ours.exists(), f"missing {ours.name}: copy it from docs/brand")
            self.assertEqual(ours.read_bytes(), theirs.read_bytes(), f"{ours.name} differs from docs/brand")

    def test_every_font_in_the_css_exists(self):
        for url in re.findall(r"url\(\"?/static/([^)\"]+)\"?\)", CSS):
            self.assertTrue((STATIC / url).exists(), url)

    def test_csp_allows_local_fonts(self):
        self.assertIn("font-src 'self'", (CONSOLE / "lola_console" / "web.py").read_text())

    def test_base_template(self):
        base = (CONSOLE / "lola_console" / "templates" / "base.html").read_text()
        for needle in ('lang="en"', 'rel="icon"', "/static/lola-bla-mark.svg", "<header", "<footer"):
            self.assertIn(needle, base)


if __name__ == "__main__":
    unittest.main()
