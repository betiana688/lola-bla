# Architecture

## System overview

![System overview](images/system-overview.png)

Two parts run on the Reachy Mini (Raspberry Pi):

- **Conversation app**: built on Pollen's conversation app. A cloud conversational agent talks live with Betiana or Lola; messaging work happens locally through tools. See [conversation-app.md](conversation-app.md).
- **Config console**: separate process, served over HTTPS on port 9443 and protected by a password. Betiana links Signal, manages groups and reads logs. See [console.md](console.md).

Both share one SQLite database, `lola.db`. See [data-model.md](data-model.md).

| Part | Choice |
|---|---|
| Hardware | Reachy Mini Wireless (Raspberry Pi CM4, 4 GB) |
| Live conversation | Cloud conversational agent: Pollen's conversation app, Hugging Face realtime backend; profile in [`profiles/lola`](../../profiles/lola/profile.md) |
| Messaging decisions | Messaging Agent, one-shot LLM call (`meta-llama/Llama-3.3-70B-Instruct` via Hugging Face Inference API) |
| Signal | `signal-cli-rest-api` in Docker, port 8080, listens on the Pi only |
| Audio | `sox` (recording, stops after about 5 s of silence) and `aplay` on the shared ALSA device (dsnoop) |
| Data | `lola.db` (SQLite, owner-only file permissions) |
| Console | Starlette and uvicorn over HTTPS (port 9443), password sign-in, one user per account |

## Messaging layers

![Messaging layers](images/messaging-layers.png)

- `handle_messaging_task.py`: the tool the conversational agent calls. Thin, no DB or Signal logic.
- `messaging_agent.py`: picks one sub-action for the task.
- `messaging_executor.py`: talks to `lola.db` and `signal-cli-rest-api`.

## Two-agent orchestration

```mermaid
flowchart TD
    A[Conversational Agent hears Betiana] --> B{Personality decides:<br/>chat, or messaging task?}
    B -->|just chat| C[Reply directly, live]
    B -->|messaging task| D[Invoke Messaging Agent<br/>with the task]
    D --> E[Messaging Agent calls a<br/>local tool via Local Tool Executor]
    E --> F{Messaging Agent:<br/>enough info to finish?}
    F -->|no - needs clarification| G[Return: question for Betiana]
    G --> H[Conversational Agent asks<br/>Betiana live, gets answer]
    H --> D
    F -->|yes - done| I[Return: summary of what happened]
    I --> J[Conversational Agent speaks<br/>the final reply, live]
    C --> K[End]
    J --> K
```

### Sequence, with the clarification loop

```mermaid
sequenceDiagram
  actor B as Betiana / Lola
  participant CA as Conversational Agent (real-time)
  participant MA as Messaging Agent
  participant LT as Local Tool Executor
  B->>CA: audio, streamed live
  CA->>CA: personality decides:<br/>just chat, or a messaging task?
  opt messaging task
    CA->>MA: task ("send a message" /<br/>"check messages")
    MA->>MA: decide which local<br/>tool to call
    MA->>LT: check_messages() / send_message(group)
    LT-->>MA: result (metadata only -<br/>message audio never leaves LT)
    alt more info needed
      MA-->>CA: "which group?" (clarification needed)
      CA-->>B: asks the question, live
      B->>CA: answer, streamed live
      CA->>MA: task, now with the answer
      MA->>LT: call the tool again
      LT-->>MA: result
    end
    MA-->>CA: done - summary for Betiana
  end
  CA-->>B: spoken reply, streamed live
```

### Who does what

```mermaid
flowchart LR
    subgraph L1["Child"]
      direction TB
      a1[Speaks a request]
      a2[Hears the reply]
    end
    subgraph L2["Conversational Agent (LLM #1, live)"]
      direction TB
      b1[Writes a plain task_description]
      b2[Speaks the final reply, in its own words]
    end
    subgraph L3["handle_messaging_task.py (Python)"]
      direction TB
      c1[Calls messaging_agent.handle_task]
      c2[Acts on the decision:<br/>DB query, or mute+record+unmute]
      c3[Builds a MINIMAL summary]
    end
    subgraph L4["Messaging Agent (LLM #2, one-shot)"]
      direction TB
      d1[Picks ONE sub-action:<br/>check_only / play_messages /<br/>need_recording / send_recording / ...]
    end
    subgraph L5["messaging_executor.py + hardware"]
      direction TB
      e1[SQLite, signal-cli-rest-api,<br/>sox/aplay]
    end
    a1 --> b1
    b1 --> c1
    c1 --> d1
    d1 --> c2
    c2 --> e1
    e1 --> c2
    c2 --> c3
    c3 --> b2
    b2 --> a2
```

## Mic handoff (mute, not release)

While a reply is recorded, the live stream to the cloud is muted, so the recording stays on the Pi.

```mermaid
sequenceDiagram
  actor Child as Child / Betiana
  participant CA as Conversational Agent (cloud)
  participant RL as record_loop (live, in-process)
  participant Tool as handle_messaging_task
  participant Dev as Shared ALSA device (dsnoop)
  Note over Child,RL: Normal conversation - record_loop continuously<br/>streams mic audio to the cloud agent
  Child->>CA: "send a message to..."
  CA->>Tool: call handle_messaging_task(...)
  Tool->>RL: stream_manager._mic_muted = True
  Note over RL: record_loop keeps running,<br/>but stops forwarding audio to the cloud
  Tool->>Dev: sox, with start and done beeps (same shared device, independent reader)
  Dev-->>Tool: Lola's recorded reply (local file only)
  Tool->>Child: aplay - local playback for review
  Tool->>RL: stream_manager._mic_muted = False
  Note over RL: Forwarding resumes -<br/>conversation continues normally
  Tool-->>CA: result (metadata only - never the audio)
  CA-->>Child: spoken confirmation, live
```

## Privacy rules

- Message audio (incoming and recorded replies) never leaves the Pi. Agents only get metadata: names, counts, timestamps.
- Only allow-listed Signal groups and registered contacts are processed.
- Every read and write of private data goes to `audit_log`.
- Signal API listens on the Pi only; the console is reachable on the home network over HTTPS and needs a password.
- The messaging assistant uses its own Hugging Face token (`local_data/hf_token`, owner-only, never committed).

## Decisions

- Built on Pollen's conversation app with a cloud conversational agent. This replaced the first, fully local prototype (`whisper.cpp` + Piper), whose speech recognition took 15–30+ s per turn on the Pi. See the [development plan](../development-plan.md).
- Two agents: the live agent handles the conversation, a one-shot Messaging Agent picks the messaging action.
- Betiana's own Signal account, no separate number for Lola.
- Filtering by allow-listed groups, not individual senders.
- Mic handoff by muting the stream, not releasing the device.
- Reachy's antennas not used for now.
- The Messaging Agent falls back to simple local keyword rules when its cloud call fails (no credits, bad token, no network). When unsure the rules only check; they never play or send. After a failure the cloud is skipped for 5 minutes, and the switch is written to the activity log.
- New messages are pulled into the database by a background sync inside the app every 2 minutes, so "check my messages" reads the database instead of waiting on Signal.
- A failed send keeps the recording, and a recording is kept only if something was heard.
- A group is chosen by its exact name: "Test" never means "Another test". An unknown or ambiguous name plays nothing.
- Console: HTTPS with a self-signed certificate; password login with a deliberately short minimum (5 characters) and a strict lockout (5 tries, 15 minutes); Keycloak later.
- Unlink is a guided action, because only the phone can revoke a linked device.
- Our files inside Pollen's clone are links into this repo (one copy of each). Data and secrets stay outside the repo. Pollen's app is pinned to commit `b9f58a3` plus a two-line patch (`app/patches`).
