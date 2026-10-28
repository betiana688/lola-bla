# Data model

All data lives in `lola.db` (SQLite), shared by the conversation app and the config console.

- **USER**: console login (one user for now).
- **ACCOUNT**: the linked Signal account (1:1 with USER for now).
- **GROUP**: allow-listed Signal groups; only active groups are visible to the app.
- **CONTACT**: registered members of a group.
- **MESSAGE**: incoming and outgoing audio messages (audio stored as a local file).
- **LOG_ENTRY**: activity log per message, including failures (shown in the console).
- **AUDIT_LOG**: every read and write of private data.

```mermaid
erDiagram
  USER ||--|| ACCOUNT : "owns (1:1 for now)"
  ACCOUNT ||--o{ GROUP : "has approved"
  GROUP ||--o{ CONTACT : "has members"
  GROUP ||--o{ MESSAGE : "contains"
  CONTACT |o--o{ MESSAGE : "sends (incoming only)"
  MESSAGE ||--o{ LOG_ENTRY : "may generate"
  USER {
    string id PK
    string username
    string password_hash
    datetime password_changed_at
    int failed_attempts
    datetime locked_until
  }
  ACCOUNT {
    string id PK
    string user_id FK "unique for now"
    string signal_number
    string status
    datetime linked_at
  }
  GROUP {
    string id PK
    string account_id FK
    string name
    string signal_group_id
    boolean is_active
  }
  CONTACT {
    string id PK
    string group_id FK
    string name
    string signal_id
  }
  MESSAGE {
    string id PK
    string group_id FK
    string contact_id FK
    string direction
    string audio_path
    datetime timestamp
    boolean played_by_reachy
  }
  LOG_ENTRY {
    string id PK
    string message_id FK
    datetime occurred_at
    string event_type
    string status
    string detail
  }
  AUDIT_LOG {
    string id PK
    string accessed_by
    string table_name
    string record_id
    string operation
    datetime occurred_at
  }
```

## Planned vs. built

This diagram is the target model. The current `schema.sql` (see [database.md](../reference/database.md)) has `groups`, `contacts`, `messages` and `log_entries`. `users`, `accounts` and `audit_log` come with the console.

> Open point: `messages.playback_position_sec` (resume paused playback) exists in `schema.sql` but is missing from this diagram.
