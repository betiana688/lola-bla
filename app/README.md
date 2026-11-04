# App code

The running Lola-Bla code. It plugs into a clone of Pollen Robotics' [`reachy_mini_conversation_app`](https://github.com/pollen-robotics/reachy_mini_conversation_app).

## Where each file goes on the robot

| In this repo | In the conversation app clone | Role |
|---|---|---|
| `tools/handle_messaging_task.py` | `src/reachy_mini_conversation_app/tools/` | Tool the Conversational Agent calls; owns mic, recording, pending-recording state |
| `tools/test_mic_handoff.py` | `src/reachy_mini_conversation_app/tools/` | Diagnostic tool proving the mic handoff |
| `local_data/messaging_agent.py` | `local_data/` | Messaging Agent: one-shot LLM call that picks the action |
| `local_data/messaging_executor.py` | `local_data/` | The only code that touches the database or Signal |
| `local_data/schema.sql` | `local_data/` | Database schema |
| [`../profiles/lola/profile.md`](../profiles/lola/profile.md) | `profiles/lola/` | Personality, safety rules, voice, tools |

`local_data/` sits at the root of the clone; `handle_messaging_task.py` finds it from there.

## Configuration

| Variable | Purpose |
|---|---|
| `LOLA_NO_BACKGROUND_SYNC` | Set to `1` to switch off the 2-minute background sync (the tests do this) |

The Signal account number is not a setting any more: it lives in the `accounts` table of the database and is set by linking from the console. The messaging assistant's own Hugging Face token lives in `local_data/hf_token` (owner-only, never committed).

## Patches to the conversation app

[`patches/pollen-conversation-app.patch`](patches/pollen-conversation-app.patch) adds two lines (`main.py`, `tools/core_tools.py`) that expose the live audio session to tools as `deps.stream_manager`. Without it, recording fails.

Tested against Pollen's commit `215880b` (2026-09-11, between v1.0.1 and v1.1.0). It does not apply to newer versions as-is. To set up a clone at that version:

```bash
git clone https://github.com/pollen-robotics/reachy_mini_conversation_app.git
cd reachy_mini_conversation_app
git checkout 215880b
git apply /path/to/lola-bla/app/patches/pollen-conversation-app.patch
```

## Diagrams

See [docs/architecture/conversation-app.md](../docs/architecture/conversation-app.md).
