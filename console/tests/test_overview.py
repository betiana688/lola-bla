"""Offline test for the contact names shown in the Groups overview."""

import sqlite3
import unittest

from lola_console import groupadmin


class People(unittest.TestCase):
    def test_names_by_group_sorted_without_case(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE contacts (group_id TEXT, name TEXT)")
        con.executemany("INSERT INTO contacts VALUES (?, ?)",
                        [("g1", "Papa"), ("g1", "abuela"), ("g2", "Mama")])
        self.assertEqual(groupadmin.people_by_group(con), {"g1": ["abuela", "Papa"], "g2": ["Mama"]})
        con.close()

    def test_no_contacts_gives_an_empty_answer(self):
        con = sqlite3.connect(":memory:")
        con.execute("CREATE TABLE contacts (group_id TEXT, name TEXT)")
        self.assertEqual(groupadmin.people_by_group(con), {})
        con.close()


if __name__ == "__main__":
    unittest.main()
