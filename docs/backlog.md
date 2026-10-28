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
- Pin `reachy_mini_conversation_app` and `signal-cli-rest-api` to specific versions
- Upstream or track as a diff the two local patches to the conversation engine
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
