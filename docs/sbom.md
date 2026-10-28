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
| `reachy_mini_conversation_app` | `github.com/pollen-robotics/reachy_mini_conversation_app` | 1.0.1, installed editable from a plain git clone — **not pinned to a specific commit** |
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
| `signal-cli-rest-api` (`bbernhard/signal-cli-rest-api`) | Docker, `latest` tag — **not pinned to a specific version** |
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

These are local, uncommitted edits to a third-party package — they'll be lost on a fresh reinstall and must be reapplied, or upstreamed as a proper contribution.

## Known gaps

- `reachy_mini_conversation_app` and `signal-cli-rest-api` both unpinned to specific versions — a future reinstall could silently pull different code
- The two local patches above exist only as manual edits, not as a tracked diff/fork
- No formal license audit has been performed on any dependency
