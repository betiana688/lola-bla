# Config console (Story 3)

![Console overview](images/console-overview.png)

- Own process and port, LAN only, one user per account.
- **Login**: credentials, one user. Keycloak maybe later.
- **Pages**: link Signal, manage groups, view logs.
- **Audit**: every action is written to `audit_log`.
- Reads and changes `lola.db`, the same database the conversation app uses. See [data-model.md](data-model.md).
- Talks to the Signal API, which listens on the Pi only.

## Linking and unlinking Signal

```mermaid
sequenceDiagram
  actor B as Betiana
  participant C as Config console
  participant A as Signal API
  participant P as Phone (Signal app)
  participant D as lola.db
  Note over B,D: 1. Linking - while signed in
  B->>C: "Link my Signal account"
  C->>A: request a linking QR code
  A-->>C: QR code
  C-->>B: shows the QR code
  B->>P: scan it (Settings, Linked devices)
  P->>A: the owner authorizes the device
  C->>A: is an account linked now?
  A-->>C: yes, this number
  C->>D: save the account + audit: account_linked
  C-->>B: linked
  Note over B,D: 2. Unlinking - from the console
  B->>C: "Unlink" and confirm
  C->>A: remove this device (exact call to be verified)
  C->>D: mark unlinked + audit: account_unlinked
  C-->>B: unlinked - Reachy now says it cannot reach messages
  Note over P,A: Unlinking from the phone works too - the console then shows "not linked"
```

## Login, password change and recovery

Recovery: a reset command on the Pi for now; a one-time code via Signal later (not built yet).

```mermaid
sequenceDiagram
  actor B as Betiana
  participant C as Config console
  participant A as Signal API
  participant D as lola.db
  participant S as Pi (over SSH)
  Note over B,S: 1. Signing in
  B->>C: username + password
  C->>D: look up the user, check the stored hash
  alt wrong password
    C->>D: audit: login_failed (repeated failures lock the login for a while)
    C-->>B: rejected
  else correct
    C->>D: audit: login_ok
    C-->>B: signed session
  end
  Note over B,S: 2. Changing the password
  B->>C: current password + new password
  C->>D: verify the current one, store the new hash
  C->>D: audit: password_changed
  C-->>B: done - other sessions end
  Note over B,S: 3. Forgot the password - first version, a command on the Pi
  B->>S: run the reset command
  S->>D: store a new hash (typed hidden), clear the lockout, end all sessions
  S->>D: audit: password_reset (actor: pi_shell)
  S-->>B: done - sign in with the new password
  Note over B,S: 4. Later, not built yet - a one-time code via Signal
  B->>C: "I forgot my password"
  C->>C: limit how often a code can be requested
  C->>A: send a short-lived code to my own Signal
  A-->>B: the code arrives in Signal
  B->>C: the code + a new password
  C->>D: check the code (one use, expires), store the new hash
  C->>D: audit: password_reset_via_signal
  C-->>B: done - other sessions end
```
