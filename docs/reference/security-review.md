# Security

How Lola-Bla is designed to stay safe. To report a problem, see [SECURITY.md](../../SECURITY.md).

The home network is assumed to be trusted. Nothing here is designed to resist a hostile device on the same Wi-Fi.

## What the console does to protect itself

- Passwords are stored as scrypt hashes. Repeated wrong passwords lock sign-in for a while, on the sign-in page, the change-password page and the remove and unlink forms.
- Sessions are signed cookies (HttpOnly, Secure, SameSite=Strict) that expire, are re-checked against the database on every request, and stop working when the password changes.
- Every form is a POST with a CSRF token and an Origin check. Pages are never cached, and a content security policy allows only the console's own files.
- The console answers only to its own host names, and the typed username of a failed sign-in is never stored.
- Destructive actions (unlink, removing a group or a contact) need a typed word and the password.
- Phone numbers are masked on every page, and numbers and IDs in log text are masked. Audio files are deleted only inside the app's audio folder, and symbolic links are never followed.
- Every action is written to the audit log with who did it. The console cannot edit or delete log entries.
- When run as a service, the console is sandboxed with the fewest rights it needs. Starting at boot is a command on the robot, not a switch in the console, because a web page that could change system services would be a way into the machine.
- Secrets (the Signal keys, tokens, the database) are kept in owner-only files and never in this repository.

## Data

The audio of messages, the contacts and the Signal keys stay on the robot. Keep backups private. See [the cloud privacy check](cloud-privacy-check.md) for what goes to cloud services.
