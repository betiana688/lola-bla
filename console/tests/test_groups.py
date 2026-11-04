"""Offline tests for the Groups page and its actions. They use a temporary database, a fake
Signal API and a temporary audio folder. Nothing real is touched."""

import os
import unittest
from pathlib import Path

from tests.test_link import LinkBase
from tests.test_web import PW, setUpModule, tearDownModule  # noqa: F401


def signal_group(internal_id, name, members=3, blocked=False):
    return {"internal_id": internal_id, "name": name, "member_count": members, "blocked": blocked}


class GroupBase(LinkBase):
    def setUp(self):
        super().setUp()
        self.state_linked()
        self.audio = Path(self.db).parent / "audio"
        self.audio.mkdir(exist_ok=True)

    def account_id(self):
        return self.row("SELECT id FROM accounts")[0][0]

    def approve(self, name, internal_id, active=1):
        group_id = "g-" + internal_id
        self.con.execute("INSERT INTO groups (id, name, signal_group_id, is_active, account_id) VALUES (?, ?, ?, ?, ?)",
                         (group_id, name, internal_id, active, self.account_id()))
        self.con.commit()
        return group_id

    def add_contact(self, group_id, name="Someone"):
        contact_id = f"c-{group_id}-{name}"
        self.con.execute("INSERT INTO contacts (id, group_id, name, signal_id) VALUES (?, ?, ?, ?)",
                         (contact_id, group_id, name, "+49000"))
        self.con.commit()
        return contact_id

    def add_message(self, group_id, path, contact_id=None):
        message_id = f"m-{group_id}-{os.path.basename(str(path))}"
        self.con.execute("INSERT INTO messages (id, group_id, contact_id, direction, audio_path, timestamp) "
                         "VALUES (?, ?, ?, 'incoming', ?, '2026-11-04 10:00:00')",
                         (message_id, group_id, contact_id, str(path)))
        self.con.commit()
        return message_id

    def post(self, path, data, headers=None):
        data = dict(data)
        data.setdefault("csrf", self.csrf())
        return self.client.post(path, data=data, headers=headers or {})

    def names(self):
        return [r[0] for r in self.row("SELECT name FROM groups ORDER BY name")]

    def count(self, table):
        return self.row(f"SELECT COUNT(*) FROM {table}")[0][0]


class Listing(GroupBase):
    def test_signed_out(self):
        other = self.new_client()
        for path in ("/groups", "/groups/add"):
            r = other.get(path)
            self.assertEqual((r.status_code, r.headers["location"]), (303, "/login"), path)
        for path in ("/groups/add", "/groups/rename", "/groups/active", "/groups/remove"):
            r = other.post(path, data={"csrf": "x", "id": "g", "internal_id": "i", "name": "n"})
            self.assertEqual(r.status_code, 303, path)

    def test_empty(self):
        self.assertIn("No groups approved yet", self.client.get("/groups").text)

    def test_lists_groups_with_counts(self):
        family = self.approve("Family", "i1")
        self.approve("Friends", "i2", active=0)
        self.add_contact(family, "Ana")
        self.add_contact(family, "Beto")
        self.add_message(family, self.audio / "x.wav")
        page = self.client.get("/groups").text
        for needle in ("Family", "Friends", "2 contacts", "1 message", "Inactive", "cannot be undone",
                       "its contacts (2)", "its messages (1)"):
            self.assertIn(needle, page)

    def test_home_links_to_the_page(self):
        self.assertIn('href="/groups"', self.client.get("/").text)


class Adding(GroupBase):
    def setUp(self):
        super().setUp()
        self.fake.group_list = [signal_group("i1", "Family", 5), signal_group("i2", "Friends", 9),
                                signal_group("i3", "Old group", 2, blocked=True), signal_group("i4", "Approved one", 4)]
        self.approve("Approved one", "i4")

    def test_candidates(self):
        page = self.client.get("/groups/add").text
        self.assertIn("Family", page)
        self.assertIn("Friends", page)
        self.assertIn("5 members", page)
        self.assertNotIn("Old group", page)
        self.assertNotIn("Approved one", page)

    def test_search(self):
        page = self.client.get("/groups/add?q=fri").text
        self.assertIn("Friends", page)
        self.assertNotIn("Family", page)
        self.assertIn("No groups match", self.client.get("/groups/add?q=zzz").text)

    def test_add(self):
        r = self.post("/groups/add", {"internal_id": "i1", "name": "  Papa   y Mama "})
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/groups"))
        self.assertEqual(self.row("SELECT name, signal_group_id, is_active, account_id FROM groups "
                                  "WHERE signal_group_id = 'i1'"), [("Papa y Mama", "i1", 1, self.account_id())])
        group_id = self.row("SELECT id FROM groups WHERE signal_group_id = 'i1'")[0][0]
        self.assertIn(("console:betiana", "group_added"), self.row("SELECT accessed_by, operation FROM audit_log"))
        self.assertEqual(self.row("SELECT record_id FROM audit_log WHERE operation = 'group_added'"), [(group_id,)])
        self.assertIn(("group_added", "ok"), self.row("SELECT event_type, status FROM log_entries"))
        self.assertIn("Group added", self.client.get("/groups").text)
        logged = str(self.row("SELECT * FROM audit_log")) + str(self.row("SELECT detail FROM log_entries"))
        self.assertNotIn("Papa y Mama", logged)

    def test_an_empty_name_uses_the_signal_name(self):
        self.post("/groups/add", {"internal_id": "i2", "name": ""})
        self.assertIn("Friends", self.names())

    def test_refusals(self):
        self.approve("Papa & Mama", "i9")
        before = self.names()
        cases = [
            ({"internal_id": "nope", "name": "X"}, "not found"),
            ({"internal_id": "i3", "name": "X"}, "not found"),
            ({"internal_id": "i4", "name": "Other"}, "already approved"),
            ({"internal_id": "i1", "name": "APPROVED   one"}, "sounds the same"),
            ({"internal_id": "i1", "name": "Papa and Mama"}, "sounds the same"),
            ({"internal_id": "i1", "name": "x" * 41}, "too long"),
            ({"internal_id": "i1", "name": "a\x01b"}, "not allowed"),
            ({"internal_id": "i1", "name": "!!!"}, "at least one letter or digit"),
        ]
        for data, expected in cases:
            with self.subTest(data=data):
                r = self.post("/groups/add", data)
                self.assertEqual((r.status_code, r.headers["location"]), (303, "/groups/add"))
                self.assertIn(expected, self.client.get("/groups/add").text)
                self.assertEqual(self.names(), before)

    def test_not_linked(self):
        self.con.execute("UPDATE groups SET account_id = NULL")  # the database refuses to delete an account that groups point at
        self.con.execute("DELETE FROM accounts")
        self.con.commit()
        self.post("/groups/add", {"internal_id": "i1", "name": "X"})
        self.assertIn("Link the Signal account first", self.client.get("/groups/add").text)
        self.assertEqual(self.names(), ["Approved one"])

    def test_api_down(self):
        self.fake.down = True
        self.assertIn("Could not read the group list", self.client.get("/groups/add").text)
        self.post("/groups/add", {"internal_id": "i1", "name": "X"})
        self.assertIn("Could not read the group list", self.client.get("/groups/add").text)
        self.assertEqual(self.names(), ["Approved one"])

    def test_csrf_and_origin(self):
        data = {"internal_id": "i1", "name": "X"}
        self.assertEqual(self.post("/groups/add", dict(data, csrf="x" * 32)).status_code, 403)
        self.assertEqual(self.post("/groups/add", data, headers={"origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.post("/groups/add", data, headers={"origin": "null"}).status_code, 403)
        self.assertEqual(self.names(), ["Approved one"])


class Renaming(GroupBase):
    def test_rename(self):
        group_id = self.approve("Family", "i1")
        r = self.post("/groups/rename", {"id": group_id, "name": " Papa "})
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/groups"))
        self.assertEqual(self.names(), ["Papa"])
        self.assertEqual(self.row("SELECT record_id FROM audit_log WHERE operation = 'group_renamed'"), [(group_id,)])
        self.assertIn("Name saved", self.client.get("/groups").text)

    def test_changing_only_the_case_is_fine(self):
        group_id = self.approve("Family", "i1")
        self.post("/groups/rename", {"id": group_id, "name": "FAMILY"})
        self.assertEqual(self.names(), ["FAMILY"])

    def test_refusals(self):
        first = self.approve("Family", "i1")
        self.approve("Friends", "i2")
        for data, expected in (({"id": first, "name": "friends"}, "sounds the same"),
                               ({"id": first, "name": ""}, "Type a name"),
                               ({"id": "nope", "name": "Whatever"}, "no longer exists")):
            with self.subTest(data=data):
                self.post("/groups/rename", data)
                self.assertIn(expected, self.client.get("/groups").text)
        self.assertEqual(self.names(), ["Family", "Friends"])


class Activating(GroupBase):
    def test_toggle(self):
        group_id = self.approve("Family", "i1")
        count = lambda op: [r[0] for r in self.row("SELECT operation FROM audit_log")].count(op)
        self.post("/groups/active", {"id": group_id, "active": "0"})
        self.assertEqual(self.row("SELECT is_active FROM groups"), [(0,)])
        self.assertEqual(count("group_deactivated"), 1)
        self.assertIn("Nothing was deleted", self.client.get("/groups").text)
        self.post("/groups/active", {"id": group_id, "active": "0"})  # already inactive: nothing new
        self.assertEqual(count("group_deactivated"), 1)
        self.post("/groups/active", {"id": group_id, "active": "1"})
        self.assertEqual(self.row("SELECT is_active FROM groups"), [(1,)])
        self.assertEqual(count("group_activated"), 1)

    def test_unknown_group(self):
        self.post("/groups/active", {"id": "nope", "active": "0"})
        self.assertIn("no longer exists", self.client.get("/groups").text)


class Removing(GroupBase):
    def setUp(self):
        super().setUp()
        self.gid = self.approve("Family", "i1")
        self.other = self.approve("Friends", "i2")
        self.ana = self.add_contact(self.gid, "Ana")
        self.add_contact(self.gid, "Beto")
        self.add_contact(self.other, "Carla")
        self.a, self.b = self.audio / "a.wav", self.audio / "b.wav"
        self.a.write_bytes(b"a")
        self.b.write_bytes(b"b")
        self.keep = self.audio / "keep.wav"
        self.keep.write_bytes(b"k")
        self.outside = Path(self.tmp.name) / "outside.wav"
        self.outside.write_bytes(b"o")
        self.first_message = self.add_message(self.gid, self.a, self.ana)
        self.add_message(self.gid, self.b)
        self.add_message(self.gid, self.outside)
        self.add_message(self.other, self.keep)
        self.con.execute("INSERT INTO log_entries (id, message_id, occurred_at, event_type, status, detail) "
                         "VALUES ('l1', ?, '2026-11-04 10:00:00', 'message_synced', 'ok', 'x')", (self.first_message,))
        self.con.commit()

    def remove(self, group_id=None, confirm="REMOVE", password=PW, token=None, headers=None):
        return self.client.post("/groups/remove", data={
            "id": group_id or self.gid, "confirm": confirm, "password": password, "csrf": token or self.csrf()},
            headers=headers or {})

    def nothing_changed(self):
        self.assertEqual(self.names(), ["Family", "Friends"])
        self.assertEqual((self.count("contacts"), self.count("messages")), (3, 4))
        self.assertTrue(self.a.exists() and self.b.exists())

    def test_the_page_says_what_will_be_deleted(self):
        page = self.client.get("/groups").text
        self.assertIn("its contacts (2)", page)
        self.assertIn("its messages (3)", page)
        self.assertIn("Type REMOVE", page)

    def test_removes_everything_of_that_group_only(self):
        r = self.remove()
        self.assertEqual((r.status_code, r.headers["location"]), (303, "/groups"))
        self.assertEqual(self.names(), ["Friends"])
        self.assertEqual(self.row("SELECT name FROM contacts"), [("Carla",)])
        self.assertEqual(self.row("SELECT audio_path FROM messages"), [(str(self.keep),)])
        self.assertFalse(self.a.exists() or self.b.exists())
        self.assertTrue(self.keep.exists())
        self.assertTrue(self.outside.exists())
        page = self.client.get("/groups").text
        self.assertIn("Deleted 2 contacts, 3 messages and 2 audio files.", page)
        self.assertIn("left alone", page)
        self.assertEqual(self.row("SELECT record_id FROM audit_log WHERE operation = 'group_removed'"), [(self.gid,)])
        self.assertIn(("group_removed", "ok"), self.row("SELECT event_type, status FROM log_entries"))
        self.assertEqual(self.row("SELECT message_id FROM log_entries WHERE id = 'l1'"), [(None,)])
        logged = str(self.row("SELECT * FROM audit_log")) + str(self.row("SELECT detail FROM log_entries"))
        self.assertNotIn("Family", logged)

    def test_wrong_word(self):
        for word in ("yes", "remove", ""):
            self.remove(confirm=word)
            self.assertIn("Type REMOVE", self.client.get("/groups").text)
        self.nothing_changed()
        self.assertEqual(self.row("SELECT failed_attempts FROM users")[0][0], 0)

    def test_wrong_password_is_counted(self):
        self.remove(password="wrong-pass-1")
        self.assertIn("password is wrong", self.client.get("/groups").text)
        self.nothing_changed()
        self.assertEqual(self.row("SELECT failed_attempts FROM users")[0][0], 1)
        self.assertIn("remove_password_failed", self.operations())
        self.assertIn(("remove_password_failed", "failed"), self.row("SELECT event_type, status FROM log_entries"))

    def test_five_wrong_passwords_lock_everything(self):
        for _ in range(5):
            self.remove(password="wrong-pass-1")
        self.remove()
        self.assertIn("ocked", self.client.get("/groups").text)
        self.nothing_changed()
        self.assertEqual(self.login(client=self.new_client()).status_code, 429)

    def test_csrf_and_origin(self):
        self.assertEqual(self.remove(token="x" * 32).status_code, 403)
        self.assertEqual(self.remove(headers={"origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.remove(headers={"origin": "null"}).status_code, 403)
        self.nothing_changed()

    def test_unknown_group(self):
        self.remove(group_id="nope")
        self.assertIn("no longer exists", self.client.get("/groups").text)
        self.nothing_changed()

    def test_symbolic_links_are_never_followed(self):
        link_path = self.audio / "link.wav"
        link_path.symlink_to(self.outside)
        self.add_message(self.gid, link_path)
        self.remove()
        self.assertTrue(self.outside.exists())
        self.assertTrue(link_path.is_symlink())

    def test_missing_and_relative_audio_paths(self):
        (self.audio / "rel.wav").write_bytes(b"r")
        self.add_message(self.gid, "rel.wav")
        self.add_message(self.gid, self.audio / "gone.wav")
        self.remove()
        self.assertFalse((self.audio / "rel.wav").exists())
        self.assertEqual(self.names(), ["Friends"])
        self.assertIn("Deleted 2 contacts, 5 messages and 3 audio files.", self.client.get("/groups").text)


if __name__ == "__main__":
    unittest.main()
