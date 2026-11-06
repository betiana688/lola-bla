# Conversation app

The voice part running on Reachy. Overall design: [architecture.md](overview.md).

## Check messages

```mermaid
sequenceDiagram
  actor Child
  participant CA as Conversational Agent
  participant Tool as MessagingTask.__call__
  participant Exec as messaging_executor.py
  participant DB as lola.db
  participant Sig as signal-cli-rest-api
  Child->>CA: "Do I have any messages?"
  CA->>Tool: handle_messaging_task(task_description=...)
  Tool->>Exec: check_messages()
  Exec->>Sig: GET /v1/receive - pull new envelopes
  Sig-->>Exec: envelopes (may include audio attachments)
  Exec->>DB: INSERT new incoming messages,<br/>audit_log entries
  Exec->>DB: SELECT unplayed messages, grouped
  DB-->>Exec: sender, day, time, audio_path (metadata only)
  Exec-->>Tool: {"status": "found_messages", "groups": [...]}
  Tool-->>CA: same dict - no raw audio bytes, ever
  CA-->>Child: "You have 2 messages from Michael, want to hear them?"
```

### Syncing from Signal (`_sync_messages` in `messaging_executor.py`)

A background thread inside the app runs this every 2 minutes. `check_messages` syncs by itself only if the last good sync is older than 5 minutes.

```mermaid
flowchart TD
    A[Fetch envelopes via /v1/receive] --> B[For each envelope]
    B --> C{Has dataMessage?}
    C -->|yes| D[content = dataMessage]
    C -->|no| E{Has syncMessage.sentMessage?}
    E -->|no| F[Skip: irrelevant envelope]
    E -->|yes| G{Timestamp matches<br/>an outgoing msg we sent?}
    G -->|yes| H[Skip: Reachy's own echo]
    G -->|no| I[content = sentMessage<br/>sender = Betiana]
    D --> J{Has groupInfo?}
    I --> J
    J -->|no| K[Skip: direct message]
    J -->|yes| L{Group in allow-list<br/>GROUPS table?}
    L -->|no| M[Skip: not allow-listed]
    L -->|yes| N{Sender matches a<br/>registered CONTACT?}
    N -->|no| O[Log: unknown_sender]
    N -->|yes| P{Has audio attachment?}
    P -->|no| Q[Skip: not a voice message]
    P -->|yes| R[Download attachment,<br/>convert to WAV via ffmpeg]
    R --> S[Insert into MESSAGES<br/>audit_log entry; a failed download is logged as download_failed]
```

## States

### Playback

```mermaid
stateDiagram-v2
  [*] --> Idle
  Idle --> Playing : group and selection chosen (all / by sender / by timestamp)
  Playing --> Paused : "Stop"
  Paused --> Playing : "Continue" (resume from saved position)
  Playing --> Idle : all selected messages played<br/>(each marked played_by_reachy)
  note right of Playing
    Played messages are not
    offered again (no replay yet)
  end note
```

**As built.** Playing plays every unplayed message of the chosen group, or only those from one sender, in order. A message is marked played only if playback really succeeded, so a failure never loses a message. There is no Stop or Continue yet, and no way to replay a message that was already played; both are in the [backlog](../backlog.md).

**As built.** Playing plays every unplayed message of the chosen group, or only those from one sender, in order. A message is marked played only if playback really succeeded, so a failure never loses a message. There is no Stop or Continue yet, and no way to replay a message that was already played; both are in the [backlog](../backlog.md).

### Recording and sending a reply

```mermaid
stateDiagram-v2
  [*] --> Idle
  Idle --> Recording : group chosen, "Send a message"
  Recording --> Paused : "pause"
  Paused --> Recording : "continue"
  Recording --> Stopped : "stop"
  Stopped --> Stopped : "replay" (plays back, stays at choice)
  Stopped --> Idle : "delete" (discarded)
  Stopped --> Sent : "send" (success)
  Stopped --> Stopped : "send" (failure, reported, retry choice)
  Sent --> [*]
```

**As built.** After the start beep the app records until about 5 seconds of silence (30 seconds at most), plays a done beep, and keeps the recording only if something was heard. The child can then hear it again, send it, or record it again (a new recording replaces the old one only if it succeeds). A failed or refused send keeps the recording. There is no pause or continue while recording and no separate "delete"; recording again replaces it. Both are in the [backlog](../backlog.md).

**As built.** After the start beep the app records until about 5 seconds of silence (30 seconds at most), plays a done beep, and keeps the recording only if something was heard. The child can then hear it again, send it, or record it again (a new recording replaces the old one only if it succeeds). A failed or refused send keeps the recording. There is no pause or continue while recording and no separate "delete"; recording again replaces it. Both are in the [backlog](../backlog.md).

## Modules

### `handle_messaging_task.py` (`MessagingTask.__call__`)

```mermaid
flowchart TD
    A[__call__ task_description] --> B[messaging_agent.handle_task<br/>if it raises: Return service_unavailable]
    B --> C{status?}
    C -->|check_only / play_messages result| D[Return as-is - already minimal]

    C -->|need_recording| NL{Signal linked?}
    NL -->|no| NLR[Return: not_linked]
    NL -->|yes| E{Group resolved?<br/>exact name, or the only active one}
    E -->|no| F[Return: need_group_clarification<br/>+ available_groups]
    E -->|yes| G[_record_message: mute mic, start beep,<br/>sox until 5 s of silence or 30 s, done beep, unmute<br/>runs in a worker thread]
    G --> H{Recording OK and<br/>something heard?}
    H -->|no| I[Return: recording_failed]
    H -->|yes| J[Store _pending_recording<br/>group_id + group_name]
    J --> K[Return: recorded + group_name]

    C -->|replay_recording| L{_pending_recording<br/>exists?}
    L -->|no| M[Return: no_pending_recording]
    L -->|yes| N[aplay the recording]
    N --> O[Return: replayed]

    C -->|send_recording| P{_pending_recording<br/>exists?}
    P -->|no| M
    P -->|yes| Q[executor.send_message]
    Q --> R{Sent OK?}
    R -->|yes| S[Clear _pending_recording<br/>Return: sent]
    R -->|no| T[Return: send_failed or not_linked<br/>the recording is KEPT]

    C -->|rerecord| U{_pending_recording<br/>exists?}
    U -->|no| M
    U -->|yes| V[_record_message again]
    V --> W[Return: recorded + group_name]
```

### `messaging_agent.py` (`handle_task`)

```mermaid
flowchart TD
    A[handle_task task_description] --> B[One-shot LLM call,<br/>SYSTEM_PROMPT + the 6 sub-tools]
    B -.->|call fails: no credits, bad token, no network| FB[Local keyword rules,<br/>cloud skipped for 5 minutes,<br/>when unsure: check only]
    FB -.-> E
    B --> C{No tool_call<br/>returned?}
    C -->|yes| D[Return: unclear]
    C -->|no| E{Which sub-tool<br/>was picked?}
    E -->|check_only| F[executor.check_messages]
    F --> G[_summarize_for_agent - strip to<br/>names, counts, timestamps]
    E -->|play_messages| H[executor.check_messages]
    H --> I[_play_filtered: aplay each match,<br/>mark_played ONLY on success]
    I --> G
    E -->|need_recording| J[Return: need_recording<br/>+ group_name if given]
    E -->|send_recording| K[Return: send_recording]
    E -->|replay_recording| L[Return: replay_recording]
    E -->|rerecord| M[Return: rerecord]
```

### `messaging_executor.py`

```mermaid
flowchart TD
    A1[check_messages] --> AL{Linked?}
    AL -->|no| ALN[Return: not_linked]
    AL -->|yes| A2[sync from Signal only if the last good sync is older than 5 min,<br/>download+convert new audio, INSERT + audit_log]
    A2 --> A3{Any unplayed<br/>messages?}
    A3 -->|no| A4[Return: no_new_messages]
    A3 -->|yes| A5[Build full-detail dict:<br/>sender, day, time, audio_path<br/>per group]
    A5 --> A6[Return: found_messages]

    B1[mark_played message_id] --> B2[UPDATE played_by_reachy=1,<br/>audit_log write]
    B2 --> B3[Return audio_path]

    C1[get_active_groups_list] --> C2[SELECT active groups,<br/>audit_log read]
    C2 --> C3[Return group list]

    D1[send_message group_id, path] --> D2[Look up signal_group_id,<br/>audit_log read]
    D2 --> D3[Encode audio + recipient ID]
    D3 --> D4[POST /v2/send]
    D4 --> D5{Success?}
    D5 -->|no| D6[Return: failed, or not_linked<br/>activity-log entry, no detail returned]
    D5 -->|yes| D7[INSERT outgoing message,<br/>audit_log write]
    D7 --> D8[Return: sent]
```

### `emotions.py`

> **Prototype only.** This module belongs to the first, local version (`prototype/emotions.py`). In the current app Reachy's expressions come from Pollen's built-in `play_emotion` tool, which the live agent calls itself with an intent such as `happy` or `confused`, and going to sleep is Pollen's `go_to_sleep` tool.

> **Prototype only.** This module belongs to the first, local version (`prototype/emotions.py`). In the current app Reachy's expressions come from Pollen's built-in `play_emotion` tool, which the live agent calls itself with an intent such as `happy` or `confused`, and going to sleep is Pollen's `go_to_sleep` tool.

```mermaid
flowchart TD
    subgraph S1["play_emotion_async(state_key) - fire and forget"]
    A[Called from speak] --> B{state_key in<br/>EMOTION_MAP?}
    B -->|no| C[Return silently]
    B -->|yes| D[Build subprocess command:<br/>enable_motors, get clip,<br/>play_move initial_goto=1.0]
    D --> E[Popen - stdout/stderr discarded]
    E --> F{Popen raised<br/>an exception?}
    F -->|yes| G[Print error, continue]
    F -->|no| H[Return immediately - runs<br/>concurrently with speech]
    end
    subgraph S2["go_to_sleep() - blocking, called once at app exit"]
    I[Called from main's finally block] --> J[enable_motors, then<br/>goto_sleep - blocks until done]
    end
```

### `sleep_robot.py` (`SleepRobot.__call__`)

Sends the robot to sleep, but only after asking and hearing a clear yes. Lola's profile lists this tool instead of Pollen's `go_to_sleep`. Pollen's tool puts the robot to sleep and stops the app (the audio stream is closed, so nothing listens while it sleeps); an antenna touch wakes the robot and starts the app again.

```mermaid
flowchart TD
    A[Someone asks Reachy to sleep] --> B[sleep_robot, confirmed false]
    B --> C[The tool remembers the ask<br/>and returns: ask first]
    C --> D[Reachy asks: do you want<br/>me to go to sleep?]
    D --> E{Clear yes?}
    E -->|no or unclear| F[Nothing happens, play on]
    E -->|yes| G[Short goodnight, then<br/>sleep_robot, confirmed true]
    G --> H{Ask 3 to 90 s ago?}
    H -->|no| C
    H -->|yes| I[Pollen go_to_sleep: robot sleeps,<br/>audio closed, app stops]
    I --> J[Antenna touch wakes the robot<br/>and starts Lola-Bla]
```

Safety: the first call can never sleep. A confirmation needs an ask at least 3 s and at most 90 s earlier, so a confirmation chained straight after the ask is refused. What the code cannot check is that a person really said yes; that part is the personality's rule (`## SLEEP` in the profile).

### `test_mic_handoff.py`

Test tool that proved the mic handoff works.

```mermaid
flowchart TD
    A[__call__] --> B[stream_manager._mic_muted = True]
    B --> C[arecord on reachymini_audio_src<br/>- shared dsnoop device, 3s]
    C --> D{Recording/playback<br/>succeeded?}
    D -->|no| E[Unmute anyway<br/>Return: error]
    D -->|yes| F[aplay on reachymini_audio_sink]
    F --> G[stream_manager._mic_muted = False]
    G --> H[Return: success]
```
