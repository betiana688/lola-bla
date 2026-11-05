# Security review

A first pass on 2026-11-04, written from what was observed on the robot and from the decisions made while building it. Items marked "to check" have not been verified. This is not an audit by anyone else.

## What is reachable on the network

| Port | What | Who can reach it | Protection |
|---|---|---|---|
| 22 | SSH | Anyone on the home network | A password login. The robot ships with a documented default password, and the author has decided to keep it for now (see Accepted risks) |
| 8000 | The Reachy Mini daemon's REST API and dashboard, according to Pollen's documentation | Anyone on the home network (it listens on every interface) | Not ours. Pollen's documentation shows apps being started and stopped with plain `curl` commands, which suggests there is no login. To check |
| 8443 | Not identified yet | Anyone on the home network (it listens on every interface) | Not ours and not reviewed. To check: which program, and whether it asks for a login |
| 9443 | The configuration console | Anyone on the home network, once it runs | HTTPS with a self-signed certificate, a password, a lockout after 5 wrong tries, signed sessions, CSRF and Origin checks |
| 8080 | The Signal API | Only this machine (127.0.0.1) | Not reachable from the network |
| 127.0.0.1:33785 | Something local | Only this machine | Not reviewed |

The home network is assumed to be trusted. Nothing here is designed to resist a hostile device on the same Wi-Fi.

## Accepted risks (the author's decisions)

- The Pi's SSH password stays the documented default. The `pollen` user also has `sudo` without a password, so anyone who gets in over SSH has full control of the robot: its microphone and camera, the database, the Signal account's keys and every secret on it.
- The console password can be as short as 5 characters. The lockout (5 wrong tries, then 15 minutes) and the slow password hashing are the protection.
- Adding a contact needs no extra password.
- The live conversation sends audio to Pollen's hosted real-time server, and no data policy could be found for it. See the [cloud privacy check](cloud-privacy-check.md).

## Secrets and files (checked 2026-11-04)

| What | Mode | Note |
|---|---|---|
| `~/.config/lola-bla` | `drwx------` | Holds the console's settings |
| `console_secret.key` | `-rw-------` | Signs the session cookies. Replacing it signs everyone out |
| `tls/key.pem` | `-rw-------` | The certificate's private key, never in the repo |
| `tls/cert.pem` | `-rw-r--r--` | The public certificate, valid until 4 November 2027 |
| `local_data/lola.db` | `-rw-------` | The database |
| `local_data/hf_token` | `-rw-------` | The messaging assistant's own token, never in the repo |

## What the console does to protect itself

- Passwords are stored as scrypt hashes. Five wrong passwords in a row lock sign-in for 15 minutes, on the sign-in page, the change-password page and the remove and unlink forms.
- Sessions are signed cookies (HttpOnly, Secure, SameSite=Strict) that last 8 hours, are re-checked against the database on every request, and stop working when the password changes.
- Every form is a POST with a CSRF token and an Origin check. Pages are never cached, and a content security policy allows only the console's own files.
- The console answers only to its own host names, and the typed username of a failed sign-in is never stored.
- Destructive actions (unlink, removing a group or a contact) need a typed word and the password. The Signal client has no way to ask for the Signal account itself to be deleted, and it has a read-only mode for trying things against the real Signal API.
- Phone numbers are masked on every page, and numbers and IDs in log text are masked. Audio files are deleted only inside the app's audio folder, and symbolic links are never followed.
- Every action is written to the audit log with who did it. The console cannot edit or delete log entries.
- When run as a service, the console is sandboxed: it sees the disk read-only except for the database folder and its own settings folder, cannot read `~/.ssh` or the messaging token, and gets no extra privileges. Starting at boot is a command on the Pi, not a switch in the console, because a web page that could change system services would be a way into the machine.

## Data and backups

Only manual copies exist, made before risky changes. The newest regular-looking copy is from the migration on 28 October. A regular database backup is still to do. The Signal keys are deliberately not backed up: if they are lost, the account is linked again from the console. The message audio is not backed up either.

## Still to check

- Which programs listen on ports 8443 and 33785, and whether the daemon on port 8000 and the programs on the other ports ask for a login.
- Whether SSH accepts password logins, and whether any firewall rules exist.
- Known vulnerabilities in the Python packages (no scan has been run).
- A reminder to renew the console's certificate before it expires.

## Not covered

Physical access to the robot, the code of Pollen's app and daemon, the Signal service itself, and tamper-evidence of the audit log (anyone with access to the database file can change it).
