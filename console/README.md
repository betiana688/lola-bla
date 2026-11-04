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

## Step 6: the web console (sign-in)

Starlette app served over HTTPS with a self-signed certificate.

| Command | What it does |
|---|---|
| `python3 console/manage.py make-cert` | Create the certificate and key in `~/.config/lola-bla/tls` (the key is owner-only and never in the repo) |
| `python3 console/run.py` | Start the console on `https://reachy-mini.local:9443/` (port: `LOLA_CONSOLE_PORT`) |

Sign-in rules: 5 wrong attempts lock sign-in for 15 minutes, and after a lock one wrong attempt re-locks. A password reset on the Pi clears the lock and ends all sessions. The certificate is valid for a year: run `make-cert` again before it expires. Extra host names: `LOLA_CONSOLE_HOSTS=name1,name2` before `make-cert` and before starting.

## Step 7: change password

Signed in, open "Change password" on the home page. It asks for the current password, then the new one twice. A wrong current password counts toward the same lockout as sign-in. Changing the password ends every other sign-in, and this browser gets a fresh session.

## Step 8a: the Signal page

Signed in, open "Signal account" on the home page. It shows whether the robot is linked, reading the Signal API's own answers, with the number masked. When the Signal API has no account, "Start linking" shows a QR code that only you can see; scan it in Signal (Settings, Linked devices). The page notices the scan, records the number, device ID and creation time, and sets the status to linked. Unlinking comes in step 8b.

| Setting | Purpose |
|---|---|
| `LOLA_SIGNAL_API` | Where the Signal API listens (default `http://localhost:8080`) |
| `LOLA_DEVICE_NAME` | The device name used when linking (default `reachy-mini`; tests use `console-test`) |
| `LOLA_DB` | Use another database (tests and trials use a copy, never the real one) |

## Step 8b: unlinking

On the Signal page the button is **Unlink**, **Clean up** or **Finish unlinking**, depending on the state. It asks for the word UNLINK and your password. It marks the robot unlinked first, unregisters the number (it can never delete the Signal account itself), deletes the app's local Signal data, and reminds you to remove `reachy-mini` from Linked devices on your phone. If a step fails, the robot stays unlinked and the page offers to finish the rest.
