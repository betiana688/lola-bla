"""Console users: create the first user, reset a password, show status.
Talks to the shared lola.db and writes an audit entry for every change. Never stores,
prints or logs a password or a hash outside the users table."""

import getpass
import os
import sqlite3
import uuid
from pathlib import Path

from . import auth

DEFAULT_DB = Path.home() / "lola-bla-agents" / "reachy_mini_conversation_app" / "local_data" / "lola.db"
NOW = "strftime('%Y-%m-%d %H:%M:%f','now')"  # UTC, with milliseconds


class UserError(Exception):
    """Something the person running the command can fix. The message is safe to show."""


def db_path() -> Path:
    return Path(os.environ.get("LOLA_DB", str(DEFAULT_DB)))


def connect(path=None):
    path = Path(path) if path else db_path()
    if not path.exists():
        raise UserError(f"database not found: {path}")
    con = sqlite3.connect(path, timeout=30)
    con.execute("PRAGMA foreign_keys = ON")
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if not {"users", "accounts", "audit_log"} <= tables:
        con.close()
        raise UserError("the database is missing the users/accounts tables (run the migration first)")
    return con


def actor() -> str:
    return f"pi_shell:{getpass.getuser()}"


def _audit(con, who, record_id, operation):
    con.execute(
        "INSERT INTO audit_log (id, accessed_by, table_name, record_id, operation, occurred_at) "
        "VALUES (?, ?, 'users', ?, ?, datetime('now'))",
        (str(uuid.uuid4()), who, record_id, operation))


def create_first_user(con, username, password, who) -> str:
    username = (username or "").strip().lower()
    problems = auth.check_username(username) + auth.check_password(password, username)
    if problems:
        raise UserError("; ".join(problems))
    if con.execute("SELECT 1 FROM users").fetchone():
        raise UserError("a user already exists (one user per Signal account for now); "
                        "use reset-password to change its password")
    accounts = con.execute("SELECT id, user_id FROM accounts").fetchall()
    if len(accounts) > 1:
        raise UserError(f"expected at most one Signal account in the database, found {len(accounts)}")
    if accounts and accounts[0][1] is not None:
        raise UserError("the Signal account already has a user")
    user_id = str(uuid.uuid4())
    pw_hash = auth.hash_password(password)
    with con:
        con.execute(f"INSERT INTO users (id, username, password_hash, password_changed_at) "
                    f"VALUES (?, ?, ?, {NOW})", (user_id, username, pw_hash))
        if accounts:
            con.execute("UPDATE accounts SET user_id = ? WHERE id = ?", (user_id, accounts[0][0]))
        _audit(con, who, user_id, "create_user")
    return user_id


def reset_password(con, password, who) -> str:
    rows = con.execute("SELECT id, username FROM users").fetchall()
    if len(rows) != 1:
        raise UserError("there is no user yet; create one with create-user" if not rows
                        else "expected exactly one user")
    user_id, username = rows[0]
    problems = auth.check_password(password, username)
    if problems:
        raise UserError("; ".join(problems))
    pw_hash = auth.hash_password(password)
    with con:
        con.execute(f"UPDATE users SET password_hash = ?, password_changed_at = {NOW}, "
                    f"failed_attempts = 0, locked_until = NULL WHERE id = ?", (pw_hash, user_id))
        _audit(con, who, user_id, "password_reset")
    return username


def status(con) -> dict:
    """What the Pi command may show: never a hash."""
    rows = con.execute(
        f"SELECT username, password_changed_at, failed_attempts, "
        f"(locked_until IS NOT NULL AND locked_until > {NOW}) FROM users").fetchall()
    accounts = con.execute("SELECT user_id FROM accounts").fetchall()
    return {
        "users": [{"username": r[0], "password_changed_at": r[1], "failed_attempts": r[2], "locked": bool(r[3])}
                  for r in rows],
        "accounts": len(accounts),
        "accounts_with_user": sum(1 for a in accounts if a[0]),
    }
