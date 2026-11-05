# Lola-Bla — Software Bill of Materials (SBOM)

Reflects the currently running system. An earlier, fully-local prototype (using `whisper.cpp` and `Piper` for on-device speech recognition/synthesis) was built and tested during development but is not part of what's deployed today — it was superseded once real-world latency testing showed the Pi's CPU couldn't meet the responsiveness the app needed.

## Operating system

| Component | Version |
|---|---|
| OS | Debian 13 (trixie) |
| Architecture | arm64 (aarch64) |

## Cloud services

| Service | Provider | Purpose |
|---|---|---|
| Realtime conversation backend | Hugging Face (via Pollen Robotics' hosted proxy, "deployed" mode) | Audio-native speech recognition + reasoning + speech synthesis for the live conversation |
| Inference API | Hugging Face | The internal Messaging Agent's tool-calling decisions |
| Model | `meta-llama/Llama-3.3-70B-Instruct` | Messaging Agent's reasoning |

**Known gap:** the exact model behind the live conversation backend isn't independently configurable from our side — it runs on Pollen's hosted proxy. Worth revisiting if stricter model-level guarantees become necessary.

## Third-party application

| Component | Source | Version |
|---|---|---|
| `reachy_mini_conversation_app` | `github.com/pollen-robotics/reachy_mini_conversation_app` | 1.0.1, pinned to commit `b9f58a3` (`app/patches/POLLEN_COMMIT`) |
| `reachy-mini` SDK | PyPI | 1.11.0 (the robot's own daemon is one version behind, at 1.10.0 — known, tracked, not yet resolved) |
| `fastrtc` | PyPI (dependency of the above) | Not independently pinned |
| `mcp` (Model Context Protocol) | PyPI (dependency of the above) | `>=1.27.1,<2` |
| `openai` (client library only — used as a generic interface, not the OpenAI service) | PyPI (dependency of the above) | `==2.28.0` |

## Python packages (direct dependencies of our own code)

| Package | Purpose |
|---|---|
| `huggingface_hub` | `InferenceClient` for the Messaging Agent's calls; also holds the stored auth token used by the realtime backend |
| `requests` | HTTP calls to the local Signal integration |

## System-level infrastructure

| Component | Detail |
|---|---|
| `signal-cli-rest-api` (`bbernhard/signal-cli-rest-api`) | Docker. On this Pi it runs as the local tag `signal-cli-rest-api-local:0.100` (version 0.100); `app/install.sh` does not set it up yet |
| SQLite | System package |
| `ffmpeg` | System package — audio format conversion |
| `sox` | System package — start/stop-on-silence recording cues and silence detection |
| Docker | System package |

## Custom code

| File | Purpose |
|---|---|
| `local_data/schema.sql` | Database schema — `groups`, `contacts`, `messages`, `log_entries`, `audit_log` |
| `local_data/messaging_executor.py` | The only code that touches the database or sends/receives Signal messages directly |
| `local_data/messaging_agent.py` | The internal Messaging Agent — decides intent via a separate LLM call |
| `src/.../tools/handle_messaging_task.py` | The tool the live conversation calls; owns microphone access, recording, and in-memory session state |
| `src/.../tools/test_mic_handoff.py` | Diagnostic tool proving the recording mechanism works safely alongside the live conversation |
| `profiles/lola/profile.md` | Personality, safety rules, voice, greeting, and enabled capabilities |

## Local patches to the third-party application

| File | Change |
|---|---|
| `main.py` | Exposes the live audio session to tools, so recording can pause/resume the conversation's own mic without disrupting it |
| `tools/core_tools.py` | Added the field that carries this reference through |

The edits are kept as a patch file (`app/patches/pollen-conversation-app.patch`) and applied by `app/install.sh` to the pinned commit. They are not yet upstreamed.

## Known gaps

- `signal-cli-rest-api` is pinned only on this Pi, as the local Docker tag `signal-cli-rest-api-local:0.100`; `app/install.sh` does not set it up yet
- The pip step of `app/install.sh` is untested (everything else in it was tested against a pristine checkout)
- No formal license audit has been performed on any dependency

## Console and tooling (added 2026-11-04)

| Component | Version | Notes |
|---|---|---|
| `starlette` | 0.52.1 | Web framework (already in the project's Python environment) |
| `uvicorn` | 0.53.0 | Web server, serves HTTPS |
| `Jinja2` | 3.1.6 | Page templates |
| `python-multipart` | 0.0.32 | Reads form posts |
| `cryptography` | 50.0.1 | Creates the self-signed certificate |
| `httpx` | 0.28.1 | Tests only |
| scrypt (Python standard library) | n/a | Password hashing; the console uses no other password library |

Versions are listed in `console/requirements.txt`.

| New custom code | Purpose |
|---|---|
| `app/local_data/background_sync.py` | Pulls new Signal messages into the database every 2 minutes |
| `console/` | The configuration console (sign-in, password, Signal page) and its tests |
| `app/install.sh`, `save.sh` | Fresh install pinned to Pollen's commit; save to GitHub after a secrets scan |
| `app/patches/` | The two edits to Pollen's app, and the exact commit they apply to |

Known gaps added 2026-11-04:

- The messaging assistant needs Hugging Face Inference credits; at zero, a local keyword fallback takes over.
- No Keycloak yet; the console password is short on purpose (5 characters).
- The Hugging Face provider that serves the messaging assistant is chosen automatically (not pinned), so its data policy is unknown; see the [cloud privacy check](reference/cloud-privacy-check.md).

### Console service (2026-11-04)

| Component | Notes |
|---|---|
| `console/install_service.sh` | Creates and manages the systemd unit `lola-console.service` (sandboxed; boot start optional) |
| systemd | Provided by the operating system (version 257 on the robot) |
