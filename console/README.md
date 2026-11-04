# Console

The config console for Lola-Bla (Story 3). Built step by step; this folder currently holds step 5, the command-line tool that creates the first console user and resets a password. The web pages come next.

| Command | What it does |
|---|---|
| `python3 console/manage.py create-user` | Create the first and only user and link it to the Signal account |
| `python3 console/manage.py reset-password` | Set a new password and clear any lockout |
| `python3 console/manage.py status` | Show whether a user exists (never shows secrets) |

Passwords are typed at a hidden prompt. Everything is written to the audit log as `pi_shell:<unix user>`.

Tests (they use a temporary database, never the real one):

    cd console && python3 -m unittest discover -s tests -t . -v
