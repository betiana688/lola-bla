# Emotions mapping

Reachy's reactions per conversation state. States match the diagrams in [conversation-app.md](../architecture/conversation-app.md).

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
