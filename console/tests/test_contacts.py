"""Offline tests for the Contacts pages. They use a temporary database, a fake Signal API and a
temporary audio folder. Nothing real is touched."""

import unittest
from pathlib import Path

from lola_console import contactadmin, link
from tests.test_groups import GroupBase
from tests.test_web import PW, SECRET, setUpModule, tearDownModule  # noqa: F401

ANA_N, BETO_N, CLEO_N, DANI_N = "+491511111111", "+491522222222", "+491533333333", "+491544444444"
ANA = {"number": ANA_N, "name": "Ana", "blocked": False}
BETO = {"number": BETO_N, "name": "Beto", "blocked": False}
CLEO = {"number": CLEO_N, "name": "Cleo", "blocked": True}
DANI = {"number": DANI_N, "name": "", "blocked": False}
ALL_NUMBERS = (ANA_N, BETO_N, CLEO_N, DANI_N)


class ContactBase(GroupBase):
    def setUp(self):
        super().setUp()
        self.gid = self.approve("Family", "i1")
        self.fake.contact_list = [ANA, BETO, CLEO, DANI]

    def ref(self, number):
        return contactadmin.ref_for(SECRET, number)

    def person(self, name, number, group_id=None):
        contact_id = f"c-{number[-4:]}-{group_id or self.gid}"  # no name inside: real IDs are random UUIDs
        self.con.execute("INSERT INTO contacts (id, group_id, name, signal_id) VALUES (?, ?, ?, ?)",
                         (contact_id, group_id or self.gid, name, number))
        self.con.commit()
        return contact_id

    def add(self, number, name="", group_id=None, headers=None, ref=None):
        return self.post("/contacts/add", {"group": group_id or self.gid,
                                           "ref": self.ref(number) if ref is None else ref, "name": name},
                         headers=headers)

    def rows(self, group_id=None):
        return self.row("SELECT name, signal_id FROM contacts WHERE group_id = ? ORDER BY name", (group_id or self.gid,))

    def everywhere(self):
        """Every place a phone number must never appear in full: audit and activity logs."""
        return str(self.row("SELECT * FROM audit_log")) + str(self.row("SELECT detail FROM log_entries"))


class Listing(ContactBase):
    def test_signed_out(self):
        other = self.new_client()
        for path in ("/contacts?group=x", "/contacts/add?group=x"):
            r = other.get(path)
            self.assertEqual((r.status_code, r.headers["location"]), (303, "/login"), path)
        for path in ("/contacts/add", "/contacts/rename", "/contacts/remove"):
            r = other.post(path, data={"csrf": "x", "id": "c", "group": "g", "ref": "r", "name": "n"})
            self.assertEqual(r.status_code, 303, path)
        self.assertEqual(self.rows(), [])

    def test_lists_contacts_with_masked_numbers_and_counts(self):
        ana = self.person("Ana", ANA_N)
        self.person("Beto", BETO_N)
        self.add_message(self.gid, self.audio / "x.wav", ana)
        page = self.client.get(f"/contacts?group={self.gid}").text
        for needle in ("Family", "Ana", "Beto", link.mask_number(ANA_N), "1 message", "0 messages", "their 1 message,"):
            self.assertIn(needle, page)
        for number in ALL_NUMBERS:
            self.assertNotIn(number, page)

    def test_empty_and_unknown_group(self):
        self.assertIn("No contacts approved", self.client.get(f"/contacts?group={self.gid}").text)
        r = self.client.get("/contacts?group=nope")
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/groups"))
        self.assertIn("no longer exists", self.client.get("/groups").text)

    def test_the_groups_page_links_here(self):
        self.assertIn(f'href="/contacts?group={self.gid}"', self.client.get("/groups").text)


class Adding(ContactBase):
    def test_candidates(self):
        self.person("Ana", ANA_N)
        page = self.client.get(f"/contacts/add?group={self.gid}").text
        self.assertIn("Beto", page)
        self.assertIn("(no name in Signal)", page)
        self.assertNotIn("Ana", page)      # already approved in this group
        self.assertNotIn("Cleo", page)     # blocked
        self.assertIn(self.ref(BETO_N), page)
        for number in ALL_NUMBERS:
            self.assertNotIn(number, page)

    def test_the_same_person_is_offered_for_another_group(self):
        self.person("Ana", ANA_N)
        other = self.approve("Friends", "i2")
        self.assertIn("Ana", self.client.get(f"/contacts/add?group={other}").text)
        self.add(ANA_N, "Ana", group_id=other)
        self.assertEqual(self.rows(other), [("Ana", ANA_N)])

    def test_search_by_name(self):
        page = self.client.get(f"/contacts/add?group={self.gid}&q=bet").text
        self.assertIn("Beto", page)
        self.assertNotIn("Ana", page)
        self.assertIn("No contacts match", self.client.get(f"/contacts/add?group={self.gid}&q=zzz").text)

    def test_add_needs_no_password(self):
        r = self.add(BETO_N, "  Beto   B ")
        self.assertEqual((r.status_code, r.headers["location"]), (303, f"/contacts?group={self.gid}"))
        self.assertEqual(self.rows(), [("Beto B", BETO_N)])
        contact_id = self.row("SELECT id FROM contacts")[0][0]
        self.assertEqual(self.row("SELECT accessed_by, record_id FROM audit_log WHERE operation = 'contact_added'"),
                         [("console:betiana", contact_id)])
        self.assertIn(("contact_added", "ok"), self.row("SELECT event_type, status FROM log_entries"))
        page = self.client.get(f"/contacts?group={self.gid}").text
        self.assertIn("Contact added", page)
        self.assertIn("Beto B", page)
        for number in ALL_NUMBERS:
            self.assertNotIn(number, page + self.everywhere())
        self.assertNotIn("Beto B", self.everywhere())

    def test_an_empty_name_uses_the_signal_name_but_not_when_there_is_none(self):
        self.add(BETO_N, "")
        self.assertEqual(self.rows(), [("Beto", BETO_N)])
        self.add(DANI_N, "")
        self.assertIn("Type a name for the contact", self.client.get(f"/contacts/add?group={self.gid}").text)
        self.assertEqual(len(self.rows()), 1)

    def test_refusals(self):
        self.person("Ana", ANA_N)
        before = self.rows()
        cases = [
            (dict(number=BETO_N, ref="x" * 24), "not found"),
            (dict(number=BETO_N, ref=""), "not found"),
            (dict(number=BETO_N, ref="\u00e9" * 24), "not found"),
            (dict(number=CLEO_N), "not found"),
            (dict(number=ANA_N, name="Other"), "already approved"),
            (dict(number=BETO_N, name="ANA"), "sounds the same"),
            (dict(number=BETO_N, name="x" * 41), "too long"),
            (dict(number=BETO_N, name="a\x01b"), "not allowed"),
            (dict(number=BETO_N, name="!!!"), "at least one letter or digit"),
        ]
        for kwargs, expected in cases:
            with self.subTest(case=expected, **{k: v for k, v in kwargs.items() if k != "number"}):
                r = self.add(**kwargs)
                self.assertEqual(r.status_code, 303)
                self.assertIn(expected, self.client.get(f"/contacts/add?group={self.gid}").text)
                self.assertEqual(self.rows(), before)

    def test_unknown_group(self):
        r = self.add(BETO_N, "Beto", group_id="nope")
        self.assertEqual(r.status_code, 303)
        self.assertIn("no longer exists", self.client.get("/groups").text)

    def test_not_linked(self):
        self.con.execute("UPDATE groups SET account_id = NULL")
        self.con.execute("DELETE FROM accounts")
        self.con.commit()
        self.add(BETO_N, "Beto")
        self.assertIn("Link the Signal account first", self.client.get(f"/contacts/add?group={self.gid}").text)
        self.assertEqual(self.rows(), [])

    def test_api_down(self):
        self.fake.down = True
        self.assertIn("Could not read your Signal contacts", self.client.get(f"/contacts/add?group={self.gid}").text)
        self.add(BETO_N, "Beto")
        self.assertIn("Could not read your Signal contacts", self.client.get(f"/contacts/add?group={self.gid}").text)
        self.assertEqual(self.rows(), [])

    def test_csrf_and_origin(self):
        data = {"group": self.gid, "ref": self.ref(BETO_N), "name": "Beto"}
        self.assertEqual(self.post("/contacts/add", dict(data, csrf="x" * 32)).status_code, 403)
        self.assertEqual(self.post("/contacts/add", data, headers={"origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.post("/contacts/add", data, headers={"origin": "null"}).status_code, 403)
        self.assertEqual(self.rows(), [])


class Renaming(ContactBase):
    def test_rename(self):
        ana = self.person("Ana", ANA_N)
        r = self.post("/contacts/rename", {"id": ana, "group": self.gid, "name": " Anita "})
        self.assertEqual((r.status_code, r.headers["location"]), (303, f"/contacts?group={self.gid}"))
        self.assertEqual(self.rows(), [("Anita", ANA_N)])
        self.assertEqual(self.row("SELECT record_id FROM audit_log WHERE operation = 'contact_renamed'"), [(ana,)])
        self.assertIn("Name saved", self.client.get(f"/contacts?group={self.gid}").text)

    def test_refusals(self):
        ana = self.person("Ana", ANA_N)
        self.person("Beto", BETO_N)
        for data, expected in (({"id": ana, "name": "beto"}, "sounds the same"),
                               ({"id": ana, "name": ""}, "Type a name"),
                               ({"id": "nope", "name": "Whatever"}, "no longer exists")):
            with self.subTest(data=data):
                self.post("/contacts/rename", dict(data, group=self.gid))
                self.assertIn(expected, self.client.get(f"/contacts?group={self.gid}").text)
        self.assertEqual(self.rows(), [("Ana", ANA_N), ("Beto", BETO_N)])

    def test_the_same_name_in_another_group_is_fine(self):
        self.person("Ana", ANA_N)
        other = self.approve("Friends", "i2")
        friend = self.person("Anita", BETO_N, other)
        self.post("/contacts/rename", {"id": friend, "group": other, "name": "Ana"})
        self.assertEqual(self.rows(other), [("Ana", BETO_N)])


class Removing(ContactBase):
    def setUp(self):
        super().setUp()
        self.ana = self.person("Ana", ANA_N)
        self.beto = self.person("Beto", BETO_N)
        self.a, self.b, self.keep = self.audio / "a.wav", self.audio / "b.wav", self.audio / "keep.wav"
        for path in (self.a, self.b, self.keep):
            path.write_bytes(b"x")
        self.outside = Path(self.tmp.name) / "outside.wav"
        self.outside.write_bytes(b"o")
        first = self.add_message(self.gid, self.a, self.ana)
        self.add_message(self.gid, self.b, self.ana)
        self.add_message(self.gid, self.outside, self.ana)
        self.add_message(self.gid, self.keep, self.beto)
        self.con.execute("INSERT INTO log_entries (id, message_id, occurred_at, event_type, status, detail) "
                         "VALUES ('l1', ?, '2026-11-04 10:00:00', 'message_synced', 'ok', 'x')", (first,))
        self.con.commit()

    def remove(self, contact_id=None, confirm="REMOVE", password=PW, token=None, headers=None):
        return self.client.post("/contacts/remove", data={
            "id": contact_id or self.ana, "group": self.gid, "confirm": confirm, "password": password,
            "csrf": token or self.csrf()}, headers=headers or {})

    def nothing_changed(self):
        self.assertEqual(self.rows(), [("Ana", ANA_N), ("Beto", BETO_N)])
        self.assertEqual(self.count("messages"), 4)
        self.assertTrue(self.a.exists() and self.b.exists())

    def test_the_page_says_what_will_be_deleted(self):
        page = self.client.get(f"/contacts?group={self.gid}").text
        self.assertIn("their 3 messages,", page)
        self.assertIn("Type REMOVE", page)

    def test_removes_the_contact_and_only_their_messages(self):
        r = self.remove()
        self.assertEqual((r.status_code, r.headers["location"]), (303, f"/contacts?group={self.gid}"))
        self.assertEqual(self.rows(), [("Beto", BETO_N)])
        self.assertEqual(self.row("SELECT audio_path FROM messages"), [(str(self.keep),)])
        self.assertFalse(self.a.exists() or self.b.exists())
        self.assertTrue(self.keep.exists())
        self.assertTrue(self.outside.exists())
        page = self.client.get(f"/contacts?group={self.gid}").text
        self.assertIn("Deleted 3 messages and 2 audio files.", page)
        self.assertIn("left alone", page)
        self.assertEqual(self.row("SELECT record_id FROM audit_log WHERE operation = 'contact_removed'"), [(self.ana,)])
        self.assertIn(("contact_removed", "ok"), self.row("SELECT event_type, status FROM log_entries"))
        self.assertEqual(self.row("SELECT message_id FROM log_entries WHERE id = 'l1'"), [(None,)])
        self.assertNotIn("Ana", self.everywhere())
        for number in ALL_NUMBERS:
            self.assertNotIn(number, page + self.everywhere())

    def test_wrong_word(self):
        for word in ("yes", "remove", ""):
            self.remove(confirm=word)
            self.assertIn("Type REMOVE", self.client.get(f"/contacts?group={self.gid}").text)
        self.nothing_changed()
        self.assertEqual(self.row("SELECT failed_attempts FROM users")[0][0], 0)

    def test_wrong_password_is_counted(self):
        self.remove(password="wrong-pass-1")
        self.assertIn("password is wrong", self.client.get(f"/contacts?group={self.gid}").text)
        self.nothing_changed()
        self.assertEqual(self.row("SELECT failed_attempts FROM users")[0][0], 1)

    def test_five_wrong_passwords_lock_everything(self):
        for _ in range(5):
            self.remove(password="wrong-pass-1")
        self.remove()
        self.assertIn("ocked", self.client.get(f"/contacts?group={self.gid}").text)
        self.nothing_changed()
        self.assertEqual(self.login(client=self.new_client()).status_code, 429)

    def test_csrf_and_origin(self):
        self.assertEqual(self.remove(token="x" * 32).status_code, 403)
        self.assertEqual(self.remove(headers={"origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.remove(headers={"origin": "null"}).status_code, 403)
        self.nothing_changed()

    def test_unknown_contact(self):
        self.remove(contact_id="nope")
        self.assertIn("no longer exists", self.client.get(f"/contacts?group={self.gid}").text)
        self.nothing_changed()

    def test_symbolic_links_are_never_followed(self):
        link_path = self.audio / "link.wav"
        link_path.symlink_to(self.outside)
        self.add_message(self.gid, link_path, self.ana)
        self.remove()
        self.assertTrue(self.outside.exists())
        self.assertTrue(link_path.is_symlink())

    def test_removing_the_group_still_takes_its_contacts(self):
        self.client.post("/groups/remove", data={"id": self.gid, "confirm": "REMOVE", "password": PW, "csrf": self.csrf()})
        self.assertEqual(self.count("contacts"), 0)


if __name__ == "__main__":
    unittest.main()
