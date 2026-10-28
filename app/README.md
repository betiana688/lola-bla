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
| `LOLA_SIGNAL_NUMBER` | The linked Signal account number, e.g. `+49...` |

## Not in this repo yet

- The two local patches to the conversation app (`main.py`, `tools/core_tools.py`) that expose the live audio session to tools. Without them, `deps.stream_manager` is missing and recording fails.

## Diagrams

See [docs/architecture/conversation-app.md](../docs/architecture/conversation-app.md).
