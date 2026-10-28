# Lola-Bla

A Reachy Mini app so Lola (too young to read or write) can hear Signal audio messages from family and send audio replies.

Personal project. Private repo.

## How it works

- Runs fully on the Reachy Mini (Raspberry Pi), no laptop or server needed.
- Uses Betiana's own Signal account via `signal-cli`.
- Only messages from **allow-listed Signal groups** are read (e.g. Spanish-speaking family, German-speaking family).
- Fixed voice commands, no LLM: on-device speech-to-text and text-to-speech.

## Phases

- **Phase 1:** Betiana uses voice commands ("check messages", "reply to …").
- **Phase 2:** Lola taps NFC figurines to trigger the same flows, no speaking needed.

## Repo layout

```
app/       Voice app running on Reachy (check messages, record and send replies)
console/   Web console for configuration and activity logs
docs/      User stories, architecture, decisions
```

## Docs

- [User stories](docs/user-stories.md)
- [Architecture](docs/architecture.md)

## Status

- Next: build Story 3 (web console).
- Later: publish as a Reachy Mini app anyone can install.
