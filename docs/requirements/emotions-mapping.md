# Emotions mapping

Reachy's reactions per conversation state. States match the diagrams in [conversation-app.md](../architecture/conversation-app.md).

> **Note (2026-11-04).** The mapping below was written for the first, local version, where code picked a clip for each state (`prototype/emotions.py`). In the current app the live agent chooses Reachy's expression itself through Pollen's `play_emotion` tool, which takes an intent such as `happy` or `confused`. The table is kept as a reference for how each situation should feel.

> **Note (2026-11-04).** The mapping below was written for the first, local version, where code picked a clip for each state (`prototype/emotions.py`). In the current app the live agent chooses Reachy's expression itself through Pollen's `play_emotion` tool, which takes an intent such as `happy` or `confused`. The table is kept as a reference for how each situation should feel.

## Idle / awake

| Trigger | Reachy behavior |
|---|---|
| App running, nothing happening | Wake-up state + idle breathing/antenna motion (built into the SDK's motion system) |

## Story 1: Reading messages

| State | Reachy behavior |
|---|---|
| Asking "which group?" | `curious1` |
| New messages found | `cheerful1` |
| No new messages | `no1` (a gentle head-shake reads as "nothing there") |
| Playing a message | `thoughtful1` (attentive, listening posture) |
| Paused | Hold current pose (stillness signals "paused") |
| All messages finished | `yes1` (a satisfied nod) |

## Story 2: Replying

| State | Reachy behavior |
|---|---|
| Asking "which group?" | `curious1` |
| Recording | `thoughtful1` (attentive listening posture, held) |
| Paused | Hold pose |
| Stopped, asking replay/send/delete | `curious1` (awaiting a decision) |
| Replay | `thoughtful1` (same as message playback) |
| Send, success | `cheerful1` + `yes1` |
| Send, failure | A "sadness"-family clip (name to be confirmed) |
| Delete | `no` |
