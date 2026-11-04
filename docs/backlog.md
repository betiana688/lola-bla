# Backlog

## General

- Always the same voice
- Always the same language (German or Spanish, no English)
- Start the app and stay idle as long as Reachy is on and the app is running
- Configuration console (Story 3)
- Publish as a Reachy Mini app
- Use an agent orchestrator
- Send alerts
- Remove unnecessary tools from Reachy (e.g. web search)
- Upgrade `reachy-mini-daemon` to match SDK 1.11.0 (deferred, needs careful system-service handling)
- Pin `signal-cli-rest-api` to a specific version
- Port the conversation-app patch to the latest Pollen version, or upstream it (currently tracked in `app/patches/`, tested against commit `215880b`)
- Revisit a single audio-native model with tool calling once more mature (e.g. Audex-30B or successors)
- Deeper safety hardening beyond the personality profile, if real usage suggests it's needed
- Scope memory facts per profile (or disable for the `lola` profile); today a fact learned under any profile can surface in any other
- Harden the mic handoff against incomplete mute/unmute (e.g. a watchdog, or auto-recovery on next launch); a crash mid-recording could leave Reachy silent until the daemon is restarted
- Database hygiene: clean up logs
- Encrypt the database
- Sensitive data in cache
- Should it be possible to link "your own" Reachy to Signal? Is this necessary?
- Move the app to the cloud or to an on-prem home server
- Choose a license before publishing

## Story 1: Reading messages

- Child-proof messages before reading them aloud (content filtering)
- Automatic cleanup of old messages and log entries after a configurable retention period (limited disk space on the Pi)
- Reachy shows emotions after the app starts
- If the intent isn't clear, Reachy asks back and offers options
- Audio post-processing for low volume on Reachy
- Real voice triggering

## Story 2: Replying

- Voice triggering of recording
- Reachy answers in the language Lola first spoke
- Confirm group
- Pause and resume recording
- Open-ended recording length (currently capped)
- Convert recorded audio to a more universal format before sending

## Done

- Amplify speaker and microphone sound (software post-processing via audio-utils)
- SBOM, README, development plan
- Git repository for the project

## Added 2026-11-04

### Story 1: Reading messages
- Play in the background with "stop" and "next". Playback currently blocks the tool until the last message ends, and the live layer errors if the child speaks meanwhile.
- The playback thread should honour a stop flag. Interrupting mid-playback started the next file before aborting.
- Investigate: the spoken summary after a check was sometimes cut off by a barge-in event.
- Test: a quiet child's voice against the 3% silence threshold of the recorder.

### Before publishing
- Remove `test_mic_handoff` from Lola's tool list.
- Decide: Hugging Face credits for the messaging assistant, or a single agent (every installer would need their own credits and token).
- Memory facts are not scoped per profile (Reachy greeted by name).
- `app/README.md` still mentions `LOLA_SIGNAL_NUMBER`, which the code no longer uses. SBOM and development plan need sox, the pins, the fallback, the background sync and Story 3 progress.
- Offline tests for the existing code are still heredocs, not files.
- The pip step of `app/install.sh` is untested. Daemon version mismatch (1.10.0 vs SDK 1.11.0) is still deferred.

### Security review: known and accepted for now (2026-11-04)
- The Pi's SSH password is still the documented default. Revisit before publishing.
- The console minimum password is 5 characters, by choice. The sign-in lockout (5 wrong tries, 15 minutes) is the protection.

### Console step 8 (2026-11-04)
- Adopt an existing Signal account: if the Signal API already has an account that the database does not know, the Signal page shows "A different account" and offers nothing. It needs the clean-up flow (step 8b) or an "adopt" button.
- QR codes: a second code requested after Cancel works (tested 2026-11-04). Still unknown: how long a code stays valid, and whether an earlier code keeps waiting.
- The link in progress and the one-time messages live in memory, so restarting the console cancels a link in progress.

### Docs and unlink (2026-11-04)
- Step 8b: decide the unlink order by experiment (phone first, then the console cleans up). Until then, the unlink diagram in `console.md` shows the order we tested in isolation, and its open point says why it cannot be the final one.
- The three PNG diagrams in `docs/architecture/images/` predate the console, the fallback and the background sync. The Mermaid versions in the text are the current ones.

### Before publishing: privacy check (2026-11-04)
- Read and record the data-retention and training policies of the two cloud services: Pollen's hosted real-time conversation proxy (it hears the child's voice) and Hugging Face Inference Providers (the messaging assistant). Story 4c items 1 and 3 depend on it.

### Console step 8b (2026-11-04)
- Not yet tested live: unlinking against a real throwaway Signal API in both orders (console first, then the phone; the phone first, then Clean up). The offline tests cover the logic.
- A link code works only once. Observed 2026-11-04: scanning the same code a second time failed with an error in Signal.
- Idea: show on the status page when the robot's device was last seen (the device list has `last_seen_timestamp`).

### Privacy check result (2026-11-04)
- Decide how to close the live-conversation gap: ask Pollen and Hugging Face in writing, or run the real-time voice engine at home. See [cloud-privacy-check.md](reference/cloud-privacy-check.md).
- Messaging assistant: use the local rules only (no cloud call), or pin one provider and read its policy.
- Review the README's privacy wording once decided, so it says exactly what leaves the robot.
