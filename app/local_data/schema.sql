CREATE TABLE users (
  id TEXT PRIMARY KEY,
  username TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  password_changed_at TEXT,
  failed_attempts INTEGER NOT NULL DEFAULT 0,
  locked_until TEXT,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE accounts (
  id TEXT PRIMARY KEY,
  user_id TEXT UNIQUE REFERENCES users(id),
  signal_number TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'linked' CHECK (status IN ('linked','unlinked')),
  device_id INTEGER,
  device_created_at TEXT,
  linked_at TEXT
);

CREATE TABLE groups (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  signal_group_id TEXT NOT NULL UNIQUE,
  is_active INTEGER NOT NULL DEFAULT 1,
  account_id TEXT REFERENCES accounts(id)
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

CREATE TABLE audit_log (
  id TEXT PRIMARY KEY,
  accessed_by TEXT NOT NULL,
  table_name TEXT NOT NULL,
  record_id TEXT,
  operation TEXT NOT NULL,
  occurred_at TEXT NOT NULL
);
