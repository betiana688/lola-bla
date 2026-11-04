#!/usr/bin/env python3
"""Console user management, run on the Pi. Standard library only.

  python3 console/manage.py create-user      create the first (and only) console user
  python3 console/manage.py reset-password   set a new password and clear any lockout
  python3 console/manage.py status           show whether a user exists (never shows secrets)

Passwords are typed at a hidden prompt, never as an argument, so they never end up in
the shell history. Database: $LOLA_DB, or the Lola-Bla default location."""

import argparse
import getpass
import sqlite3
import sys

from lola_console import auth, users


def _ask_new_password(read_password):
    first = read_password(f"New password (hidden, at least {auth.MIN_PASSWORD_LENGTH} characters): ")
    second = read_password("Type it again: ")
    if first != second:
        raise users.UserError("the two passwords do not match")
    return first


def main(argv=None, read_password=getpass.getpass, read_line=input, out=print) -> int:
    parser = argparse.ArgumentParser(prog="manage.py", description="Lola-Bla console users")
    parser.add_argument("command", choices=["create-user", "reset-password", "status", "make-cert"])
    args = parser.parse_args(argv)
    if args.command == "make-cert":
        from lola_console import tls
        info = tls.make_certificate()
        out(f"Certificate: {info['cert_path']}")
        out(f"Private key (owner-only): {info['key_path']}")
        out(f"Valid for: {', '.join(info['names'])}")
        out(f"Expires: {info['expires']} (run make-cert again before then)")
        out(f"SHA-256 fingerprint: {info['fingerprint']}")
        return 0
    try:
        con = users.connect()
        try:
            if args.command == "status":
                info = users.status(con)
                if not info["users"]:
                    out("No user yet. Create one with: python3 console/manage.py create-user")
                for u in info["users"]:
                    out(f"User: {u['username']}")
                    out(f"Password last changed: {u['password_changed_at']} (UTC)")
                    out(f"Failed sign-ins in a row: {u['failed_attempts']}")
                    out(f"Locked right now: {'yes' if u['locked'] else 'no'}")
                out(f"Signal accounts in the database: {info['accounts']} ({info['accounts_with_user']} with a user)")
            elif args.command == "create-user":
                username = read_line("Username (3-32 characters: a-z, 0-9, dot, dash, underscore): ").strip().lower()
                password = _ask_new_password(read_password)
                users.create_first_user(con, username, password, users.actor())
                out(f"Created user '{username}' and linked it to the Signal account.")
            else:
                password = _ask_new_password(read_password)
                username = users.reset_password(con, password, users.actor())
                out(f"New password set for '{username}'. Any lockout is cleared.")
        finally:
            con.close()
    except users.UserError as e:
        out(f"Not done: {e}")
        return 1
    except (KeyboardInterrupt, EOFError):
        out("Cancelled, nothing changed.")
        return 1
    except sqlite3.Error as e:
        out(f"Database problem ({type(e).__name__}). Nothing changed.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
