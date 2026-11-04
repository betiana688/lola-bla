# Lola App — Database Reference

SQLite database at `~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db`, created from [`app/local_data/schema.sql`](../../app/local_data/schema.sql). This is the manual reference for managing groups and contacts until the console pages for them exist (Story 3).

## Schema

The source of truth is [`app/local_data/schema.sql`](../../app/local_data/schema.sql); it is not repeated here, so it cannot go stale. The tables are:

| Table | Holds |
|---|---|
| `users` | The console user (one for now): name, scrypt password hash, lockout counters |
| `accounts` | The Signal account: number, `linked` or `unlinked`, the robot's device ID and creation time, and the user it belongs to |
| `groups` | Approved Signal groups, each tied to an account (`account_id`) |
| `contacts` | Approved people, per group |
| `messages` | Incoming and outgoing voice messages |
| `log_entries` | The activity log (failures and notable events) |
| `audit_log` | Who touched which table, and when |

**Notes on key fields:**
- `groups.signal_group_id` — always the raw `internal_id` form from the Signal API (matches what incoming messages use). The `group.`-prefixed base64 form needed for *sending* (Story 2) is derived on the fly from this, never stored separately.
- `contacts.signal_id` — a person's Signal phone number (or UUID). Being a member of the Signal group is **not** enough on its own — a sender must also have a `contacts` row to be treated as a known sender (Story 3's allow-list rule).
- `messages.played_by_reachy` — Reachy's own "have I read this aloud yet" flag, independent of Signal's read/unread state.
- `accounts.device_id` and `accounts.device_created_at`: the robot's device on the Signal account. The ID is per account (the live robot is 2, a test device on the same account was 3), so both are stored.
- `groups.account_id`: which Signal account the group belongs to. When adding a group by hand, set it to the account's `id` (`SELECT id FROM accounts;`).
- `users.password_hash`: scrypt, with its settings stored inside the hash. Never printed or logged.

## Setup / one-off commands

**Create the database from the schema:**
```bash
sqlite3 ~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db < ~/lola-bla/app/local_data/schema.sql
```

**List all tables (sanity check):**
```bash
sqlite3 ~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db ".tables"
```

## Managing groups

The console's Groups page does this now (add from Signal, rename, deactivate or activate, remove). The commands below still work.

**Register an allow-listed group:**
```bash
sqlite3 ~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db "INSERT INTO groups (id, name, signal_group_id, is_active) VALUES ('grp-1', 'Lola, Michi & Bet', 'SIGNAL_INTERNAL_GROUP_ID', 1);"
```

**List all groups:**
```bash
sqlite3 ~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db "SELECT id, name, signal_group_id, is_active FROM groups;"
```

**Deactivate a group (without deleting its history):**
```bash
sqlite3 ~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db "UPDATE groups SET is_active = 0 WHERE id = 'grp-1';"
```

## Managing contacts

The console's Contacts page does this now (add from your Signal contacts, rename, remove). The commands below still work.

**Register a contact within a group** (required before Reachy will treat their messages as legitimate — see Story 3):
```bash
sqlite3 ~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db "INSERT INTO contacts (id, group_id, name, signal_id) VALUES ('contact-1', 'grp-1', 'Betiana', 'THEIR_SIGNAL_NUMBER');"
```

**List all contacts:**
```bash
sqlite3 ~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db "SELECT id, group_id, name, signal_id FROM contacts;"
```

**Update a contact's number:**
```bash
sqlite3 ~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db "UPDATE contacts SET signal_id = 'NEW_NUMBER' WHERE id = 'contact-1';"
```

**Remove a contact** (revokes their ability to send to / be heard by Lola):
```bash
sqlite3 ~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db "DELETE FROM contacts WHERE id = 'contact-1';"
```

## Inspecting messages

**List all synced messages:**
```bash
sqlite3 ~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db "SELECT id, contact_id, audio_path, played_by_reachy FROM messages;"
```

**List unplayed messages for a group:**
```bash
sqlite3 ~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db "SELECT id, contact_id, audio_path, timestamp FROM messages WHERE group_id = 'grp-1' AND played_by_reachy = 0 ORDER BY timestamp;"
```

## Inspecting logs (debugging)

The console's Logs page shows both logs now, with filters and masking. The commands below still work.

**Most recent log entries:**
```bash
sqlite3 ~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db "SELECT * FROM log_entries ORDER BY occurred_at DESC LIMIT 5;"
```

**Only failures/ignored events:**
```bash
sqlite3 ~/lola-bla-agents/reachy_mini_conversation_app/local_data/lola.db "SELECT occurred_at, event_type, status, detail FROM log_entries WHERE status != 'success' ORDER BY occurred_at DESC;"
```

---
*This file will become redundant once the config console (Story 3) exists — keeping it as reference in the meantime, and as documentation of what the console needs to replicate.*
