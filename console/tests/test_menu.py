"""Offline tests for the user menu and the jump buttons that every signed-in page shows."""

from tests.test_web import CSRF_RE, WebBase, setUpModule, tearDownModule  # noqa: F401

PAGES = ("/", "/groups", "/logs", "/password")


class Menu(WebBase):
    def test_signed_out_pages_have_no_menu(self):
        html = self.client.get("/login").text
        self.assertNotIn('class="menu"', html)
        self.assertNotIn('class="jump"', html)

    def test_every_signed_in_page_has_the_menu_and_jump_buttons(self):
        self.login()
        for page in PAGES:
            html = self.client.get(page).text
            for needle in ('class="menu"', 'action="/logout"', 'href="/groups"', 'href="/logs"',
                           'href="/signal"', 'href="/password"', 'class="jump"', 'id="bottom"'):
                self.assertIn(needle, html, f"{page} is missing {needle}")

    def test_sign_out_from_the_menu_works(self):
        self.login()
        token = CSRF_RE.search(self.client.get("/groups").text).group(1)
        r = self.client.post("/logout", data={"csrf": token})
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/login"))
        self.assertEqual(self.client.get("/groups").status_code, 303)

    def test_no_show_text_buttons_are_left(self):
        from pathlib import Path
        for f in (Path(__file__).resolve().parents[1] / "lola_console" / "templates").glob("*.html"):
            self.assertNotIn('aria-pressed="false">Show</button>', f.read_text(), f.name)
