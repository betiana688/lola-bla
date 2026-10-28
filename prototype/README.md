# Phase 1 prototype (superseded)

The first, fully local version: rule-based dialogue, `whisper.cpp` for speech recognition, Piper for speech, keyword matching for intents. It worked end to end, but speech recognition on the Pi's CPU took 15–30+ seconds per turn, so the app was rebuilt around a real-time cloud conversation. See the [development plan](../docs/development-plan.md).

Kept for reference only. Not used by the running app.

| File | What it did |
|---|---|
| `sync.py` | Pulled messages from Signal, filtered by allow-listed groups and contacts, logged skipped ones |
| `send_message.py` | Sent a voice message to a group via `/v2/send` |
| `send_group.py` | Asked which group to send to (keyword matching, one retry) |
| `reply_decision.py` | Replay / send / delete loop after recording |
| `audio_utils.py` | Released/acquired the audio hardware, recording, mic gain |
| `emotions.py` | Emotion clips per dialogue state, wake up / go to sleep |
| `record_test.py` | Manual recording test |

`dialogue.py` (the dialogue manager) and the `whisper.cpp`/Piper setup are not included.

Ideas worth carrying over: `sync.py` logs `unknown_sender` and `non_audio_message` to `log_entries`; the current executor skips those silently. The console's activity log (Story 3) will need them.
