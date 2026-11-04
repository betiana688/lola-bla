"""Offline tests for the console's users and passwords. Run from the console folder:
    python3 -m unittest discover -s tests -t . -v
They use a temporary database built from the real schema. Your real database is never touched."""

import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

import manage
from lola_console import auth, users

SCHEMA = Path(__file__).resolve().parents[2] / "app" / "local_data" / "schema.sql"
PW1 = "blue-tree-sky-9"
PW2 = "green-lake-moon-4"
WHO = "pi_shell:test"


class Hashing(unittest.TestCase):
    def test_roundtrip(self):
        h = auth.hash_password(PW1)
        self.assertTrue(auth.verify_password(PW1, h))
        self.assertFalse(auth.verify_password(PW1 + "x", h))

    def test_salted(self):
        self.assertNotEqual(auth.hash_password(PW1), auth.hash_password(PW1))

    def test_hash_hides_password(self):
        h = auth.hash_password(PW1)
        self.assertTrue(h.startswith("scrypt$"))
        self.assertNotIn("blue", h)

    def test_malformed_hashes_rejected(self):
        for bad in ["", "x", "scrypt$1$2$3", "bcrypt$1$1$1$AAAA$AAAA", "scrypt$a$b$c$d$e",
                    "scrypt$3$8$1$AAAA$AAAA", None]:
            self.assertFalse(auth.verify_password(PW1, bad), bad)

    def test_speed(self):
        start = time.perf_counter()
        auth.hash_password(PW1)
        took = time.perf_counter() - start
        print(f"\n  one scrypt hash takes {took:.2f} s on this machine ... ", end="")
        self.assertLess(took, 5)


class Policy(unittest.TestCase):
    def test_short_rejected(self):
        self.assertTrue(auth.check_password("abcd", "betiana"))

    def test_minimum_is_five(self):
        self.assertTrue(auth.check_password("abcd", "betiana"))
        self.assertEqual(auth.check_password("abcde", "betiana"), [])
        self.assertTrue(auth.check_password("12345", "betiana"))

    def test_ok_password(self):
        self.assertEqual(auth.check_password(PW1, "betiana"), [])

    def test_username_inside_rejected(self):
        self.assertTrue(auth.check_password("betiana-is-great-2", "betiana"))

    def test_repetitive_rejected(self):
        self.assertTrue(auth.check_password("aaaaaaaaaaaaaa", "betiana"))

    def test_easy_parts_rejected(self):
        self.assertTrue(auth.check_password("my-password-is-long", "betiana"))
        self.assertTrue(auth.check_password("qwertyuiop-1234", "betiana"))

    def test_unicode_ok(self):
        self.assertEqual(auth.check_password("frühstück-mit-käse-77", "betiana"), [])

    def test_too_long(self):
        self.assertTrue(auth.check_password("a-b" * 50, "betiana"))

    def test_usernames(self):
        for ok in ["betiana", "lola.bla", "a-b_c1"]:
            self.assertEqual(auth.check_username(ok), [], ok)
        for bad in ["ab", "Betiana", "a b", "x" * 33, ".abc", "bé tiana", ""]:
            self.assertTrue(auth.check_username(bad), bad)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.chmod(self.tmp.name, 0o700)
        self.db = Path(self.tmp.name) / "test.db"
        con = sqlite3.connect(self.db)
        con.executescript(SCHEMA.read_text())
        con.execute("INSERT INTO accounts (id, signal_number, status) VALUES ('acc1', 'test-number', 'linked')")
        con.commit()
        con.close()
        self.con = users.connect(self.db)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()

    def count(self, table):
        return self.con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


class CreateUser(Base):
    def test_creates_links_and_audits(self):
        uid = users.create_first_user(self.con, "betiana", PW1, WHO)
        name, pw_hash, failed, locked = self.con.execute(
            "SELECT username, password_hash, failed_attempts, locked_until FROM users").fetchone()
        self.assertEqual(name, "betiana")
        self.assertTrue(auth.verify_password(PW1, pw_hash))
        self.assertEqual((failed, locked), (0, None))
        self.assertEqual(self.con.execute("SELECT user_id FROM accounts").fetchone()[0], uid)
        self.assertEqual(self.con.execute(
            "SELECT accessed_by, table_name, record_id, operation FROM audit_log").fetchall(),
            [(WHO, "users", uid, "create_user")])

    def test_one_user_only(self):
        users.create_first_user(self.con, "betiana", PW1, WHO)
        with self.assertRaises(users.UserError):
            users.create_first_user(self.con, "someone", PW2, WHO)
        self.assertEqual(self.count("users"), 1)

    def test_username_lowercased(self):
        users.create_first_user(self.con, "  Betiana ", PW1, WHO)
        self.assertEqual(self.con.execute("SELECT username FROM users").fetchone()[0], "betiana")

    def test_weak_password_changes_nothing(self):
        with self.assertRaises(users.UserError):
            users.create_first_user(self.con, "betiana", "abcd", WHO)
        self.assertEqual((self.count("users"), self.count("audit_log")), (0, 0))

    def test_no_account(self):
        self.con.execute("DELETE FROM accounts")
        self.con.commit()
        with self.assertRaises(users.UserError):
            users.create_first_user(self.con, "betiana", PW1, WHO)

    def test_two_accounts(self):
        self.con.execute("INSERT INTO accounts (id, signal_number, status) VALUES ('acc2', 'other', 'linked')")
        self.con.commit()
        with self.assertRaises(users.UserError):
            users.create_first_user(self.con, "betiana", PW1, WHO)

    def test_password_never_on_disk(self):
        users.create_first_user(self.con, "betiana", PW1, WHO)
        self.assertNotIn(PW1.encode(), self.db.read_bytes())


class Reset(Base):
    def setUp(self):
        super().setUp()
        users.create_first_user(self.con, "betiana", PW1, WHO)

    def test_reset_clears_lockout_and_audits(self):
        self.con.execute("UPDATE users SET failed_attempts = 5, locked_until = '2999-01-01 00:00:00.000'")
        self.con.commit()
        before = self.con.execute("SELECT password_changed_at FROM users").fetchone()[0]
        time.sleep(0.01)
        self.assertEqual(users.reset_password(self.con, PW2, WHO), "betiana")
        pw_hash, failed, locked, after = self.con.execute(
            "SELECT password_hash, failed_attempts, locked_until, password_changed_at FROM users").fetchone()
        self.assertTrue(auth.verify_password(PW2, pw_hash))
        self.assertFalse(auth.verify_password(PW1, pw_hash))
        self.assertEqual((failed, locked), (0, None))
        self.assertGreater(after, before)
        self.assertEqual([r[0] for r in self.con.execute("SELECT operation FROM audit_log ORDER BY rowid")],
                         ["create_user", "password_reset"])

    def test_weak_reset_rejected_and_changes_nothing(self):
        before = self.con.execute("SELECT password_hash FROM users").fetchone()[0]
        with self.assertRaises(users.UserError):
            users.reset_password(self.con, "abcd", WHO)
        self.assertEqual(self.con.execute("SELECT password_hash FROM users").fetchone()[0], before)
        self.assertEqual(self.count("audit_log"), 1)

    def test_status_shows_no_secrets(self):
        self.con.execute("UPDATE users SET locked_until = '2999-01-01 00:00:00.000'")
        self.con.commit()
        info = users.status(self.con)
        self.assertTrue(info["users"][0]["locked"])
        self.assertEqual((info["accounts"], info["accounts_with_user"]), (1, 1))
        self.assertNotIn("hash", " ".join(info["users"][0].keys()))
        self.assertNotIn(PW1, str(info))


class ResetNoUser(Base):
    def test_reset_without_user(self):
        with self.assertRaises(users.UserError):
            users.reset_password(self.con, PW1, WHO)


class Cli(Base):
    def setUp(self):
        super().setUp()
        os.environ["LOLA_DB"] = str(self.db)

    def tearDown(self):
        os.environ.pop("LOLA_DB", None)
        super().tearDown()

    def run_cli(self, argv, lines=(), passwords=()):
        lines, passwords, out = iter(lines), iter(passwords), []
        rc = manage.main(argv, read_password=lambda prompt: next(passwords),
                         read_line=lambda prompt: next(lines), out=out.append)
        return rc, "\n".join(out)

    def test_create(self):
        rc, out = self.run_cli(["create-user"], lines=["Betiana"], passwords=[PW1, PW1])
        self.assertEqual(rc, 0)
        self.assertIn("Created user 'betiana'", out)
        self.assertEqual(self.count("users"), 1)

    def test_mismatch(self):
        rc, out = self.run_cli(["create-user"], lines=["betiana"], passwords=[PW1, PW2])
        self.assertEqual(rc, 1)
        self.assertIn("do not match", out)
        self.assertEqual(self.count("users"), 0)

    def test_second_create_refused(self):
        self.run_cli(["create-user"], lines=["betiana"], passwords=[PW1, PW1])
        rc, out = self.run_cli(["create-user"], lines=["other"], passwords=[PW2, PW2])
        self.assertEqual(rc, 1)
        self.assertIn("already exists", out)

    def test_reset(self):
        users.create_first_user(self.con, "betiana", PW1, WHO)
        rc, out = self.run_cli(["reset-password"], passwords=[PW2, PW2])
        self.assertEqual(rc, 0)
        self.assertTrue(auth.verify_password(PW2, self.con.execute("SELECT password_hash FROM users").fetchone()[0]))

    def test_output_never_has_password(self):
        _, out = self.run_cli(["create-user"], lines=["betiana"], passwords=[PW1, PW1])
        self.assertNotIn(PW1, out)
        self.assertNotIn("scrypt$", out)

    def test_status_no_user(self):
        rc, out = self.run_cli(["status"])
        self.assertEqual(rc, 0)
        self.assertIn("No user yet", out)


if __name__ == "__main__":
    unittest.main()
