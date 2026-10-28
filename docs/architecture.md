# Architecture

## Overview

```
Mic → STT (on-device) → fixed intents → signal-cli → Signal
Signal → signal-cli → filter (allow-listed groups) → audio playback / TTS → Speaker
Web console → config (groups, contacts) + activity log
```

## Components

| Part | Choice |
|---|---|
| Hardware | Reachy Mini Wireless (Raspberry Pi CM4, 4 GB) |
| Speech-to-text | On-device, e.g. whisper.cpp |
| Text-to-speech | On-device |
| Signal | signal-cli, Betiana's own account |
| Intents | Fixed (check messages, reply to X), no LLM |
| Config | Web console (Story 3) |

## Data model

- **Group**: a Signal group; only allow-listed groups are visible to the app.
- **Contact**: belongs to a group.

## Decisions

- Not built on the Baby Reachy-Mini Companion pipeline: it never worked and needed the laptop running Ollama.
- Fully self-contained on the Pi.
- Betiana's own Signal account, no separate number for Lola.
- Filtering by allow-listed groups, not by individual senders.
- Reachy's antennas not used for now (maybe later for visual feedback).
