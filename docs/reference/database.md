# Lola App — Database Reference

SQLite database at `~/lola-bla-app/app/data/lola.db`, created from `~/lola-bla-app/app/schema.sql`. This is the manual reference for managing groups/contacts until the config console (Story 3) exists.

## Schema

The source of truth is [`app/local_data/schema.sql`](../../app/local_data/schema.sql), which also has the `audit_log` table. The excerpt below predates it.

```sql
CREATE TABLE groups (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  signal_group_id TEXT NOT NULL UNIQUE,
  is_active INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE contacts (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL REFERENCES groups(id),
  name TEXT NOT NULL,
  signal_id TEXT NOT NULL
);

CREATE TABLE messages (
  id TEXT PRIMARY KEY,
  group_id TEXT NOT NULL REFERENCES groups(id),
  contact_id TEXT REFERENCES contacts(id),
  direction TEXT NOT NULL CHECK (direction IN ('incoming', 'outgoing')),
  audio_path TEXT NOT NULL,
  timestamp TEXT NOT NULL,
  played_by_reachy INTEGER NOT NULL DEFAULT 0,
  playback_position_sec INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE log_entries (
  id TEXT PRIMARY KEY,
  message_id TEXT REFERENCES messages(id),
  occurred_at TEXT NOT NULL,
  event_type TEXT NOT NULL,
  status TEXT NOT NULL,
  detail TEXT
);
```

**Notes on key fields:**
- `groups.signal_group_id` — always the raw `internal_id` form from the Signal API (matches what incoming messages use). The `group.`-prefixed base64 form needed for *sending* (Story 2) is derived on the fly from this, never stored separately.
- `contacts.signal_id` — a person's Signal phone number (or UUID). Being a member of the Signal group is **not** enough on its own — a sender must also have a `contacts` row to be treated as a known sender (Story 3's allow-list rule).
- `messages.played_by_reachy` — Reachy's own "have I read this aloud yet" flag, independent of Signal's read/unread state.

## Setup / one-off commands

**Create the database from the schema:**
```bash
sqlite3 ~/lola-bla-app/app/data/lola.db < ~/lola-bla-app/app/schema.sql
```

**List all tables (sanity check):**
```bash
sqlite3 ~/lola-bla-app/app/data/lola.db ".tables"
```

## Managing groups

**Register an allow-listed group:**
```bash
sqlite3 ~/lola-bla-app/app/data/lola.db "INSERT INTO groups (id, name, signal_group_id, is_active) VALUES ('grp-1', 'Lola, Michi & Bet', 'SIGNAL_INTERNAL_GROUP_ID', 1);"
```

**List all groups:**
```bash
sqlite3 ~/lola-bla-app/app/data/lola.db "SELECT id, name, signal_group_id, is_active FROM groups;"
```

**Deactivate a group (without deleting its history):**
```bash
sqlite3 ~/lola-bla-app/app/data/lola.db "UPDATE groups SET is_active = 0 WHERE id = 'grp-1';"
```

## Managing contacts

**Register a contact within a group** (required before Reachy will treat their messages as legitimate — see Story 3):
```bash
sqlite3 ~/lola-bla-app/app/data/lola.db "INSERT INTO contacts (id, group_id, name, signal_id) VALUES ('contact-1', 'grp-1', 'Betiana', 'THEIR_SIGNAL_NUMBER');"
```

**List all contacts:**
```bash
sqlite3 ~/lola-bla-app/app/data/lola.db "SELECT id, group_id, name, signal_id FROM contacts;"
```

**Update a contact's number:**
```bash
sqlite3 ~/lola-bla-app/app/data/lola.db "UPDATE contacts SET signal_id = 'NEW_NUMBER' WHERE id = 'contact-1';"
```

**Remove a contact** (revokes their ability to send to / be heard by Lola):
```bash
sqlite3 ~/lola-bla-app/app/data/lola.db "DELETE FROM contacts WHERE id = 'contact-1';"
```

## Inspecting messages

**List all synced messages:**
```bash
sqlite3 ~/lola-bla-app/app/data/lola.db "SELECT id, contact_id, audio_path, played_by_reachy FROM messages;"
```

**List unplayed messages for a group:**
```bash
sqlite3 ~/lola-bla-app/app/data/lola.db "SELECT id, contact_id, audio_path, timestamp FROM messages WHERE group_id = 'grp-1' AND played_by_reachy = 0 ORDER BY timestamp;"
```

## Inspecting logs (debugging)

**Most recent log entries:**
```bash
sqlite3 ~/lola-bla-app/app/data/lola.db "SELECT * FROM log_entries ORDER BY occurred_at DESC LIMIT 5;"
```

**Only failures/ignored events:**
```bash
sqlite3 ~/lola-bla-app/app/data/lola.db "SELECT occurred_at, event_type, status, detail FROM log_entries WHERE status != 'success' ORDER BY occurred_at DESC;"
```

---
*This file will become redundant once the config console (Story 3) exists — keeping it as reference in the meantime, and as documentation of what the console needs to replicate.*
