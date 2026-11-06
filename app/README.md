# App code

The running Lola-Bla code. It plugs into a clone of Pollen Robotics' [`reachy_mini_conversation_app`](https://github.com/pollen-robotics/reachy_mini_conversation_app).

## Which file does what

`install.sh` links each of these files into the clone, so there is one copy of each and nothing to copy by hand.

| In this repo | In the conversation app clone | Role |
|---|---|---|
| `tools/handle_messaging_task.py` | `src/reachy_mini_conversation_app/tools/` | Tool the Conversational Agent calls; owns mic, recording, pending-recording state |
| `tools/test_mic_handoff.py` | `src/reachy_mini_conversation_app/tools/` | Diagnostic tool proving the mic handoff |
| `local_data/messaging_agent.py` | `local_data/` | Messaging Agent: one-shot LLM call that picks the action |
| `local_data/messaging_executor.py` | `local_data/` | The only code that touches the database or Signal |
| `local_data/background_sync.py` | `local_data/` | Pulls new Signal messages into the database every 2 minutes, inside the app |
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

Pinned to Pollen's commit `b9f58a3` (see [`patches/POLLEN_COMMIT`](patches/POLLEN_COMMIT)). The patch applies to it cleanly (checked on a fresh checkout), and `install.sh` does the clone, checkout and patch for you. An earlier note named `215880b` (2026-09-11), which is five source files older than what we run. To do it by hand:

```bash
git clone https://github.com/pollen-robotics/reachy_mini_conversation_app.git
cd reachy_mini_conversation_app
git checkout b9f58a3
git apply /path/to/lola-bla/app/patches/pollen-conversation-app.patch
```

## Diagrams

See [docs/architecture/conversation-app.md](../docs/architecture/conversation-app.md).

## As a Reachy Mini app (`lola_bla`)

- Package in `app/` (`src/lola_bla`), console as package in `console/`. Installed editable into `/venvs/apps_venv`
  (`uv pip install -e` the conversation app clone, `console/` and `app/`), so `local_data` and `profiles` keep working.
- The app sets the Lola profile with Pollen's own `set_custom_profile` and refuses to start if it is not active.
- The camera flag `--no-camera` is passed to the conversation app (open question: Control still shows a camera view).
- Pollen's settings page without a login is switched off (`dont_start_webserver = True`).
- Ports: 9443 console (https, login), 9080 landing page (plain http, static). Environment: `LOLA_CONSOLE_PORT`, `LOLA_LANDING_PORT`.
- Do not start `lola_bla` from Control without the landing page: Control stops apps whose web address is unreachable.
