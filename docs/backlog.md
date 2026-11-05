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
- The Pi's SSH password is still the documented default, and `pollen` has sudo without a password, so anyone who gets in over SSH has full control. Accepted by the author for now; revisit before publishing. See the security review.
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
- Tested live on 2026-11-04 against a throwaway Signal API and a copy of the database. The first run's audit trail shows link_started, account_linked, unlink_started, account_unlinked. The author then repeated the missing parts with a phone (a second link, the phone-first order with Clean up, and the wrong-password refusal) and reports that all went well. Those later runs were not inspected in the logs.
- A link code works only once. Observed 2026-11-04: scanning the same code a second time failed with an error in Signal.
- Idea: show on the status page when the robot's device was last seen (the device list has `last_seen_timestamp`).

### Privacy check result (2026-11-04)
- Decide how to close the live-conversation gap: ask Pollen and Hugging Face in writing, or run the real-time voice engine at home. See [cloud-privacy-check.md](reference/cloud-privacy-check.md).
- Messaging assistant: use the local rules only (no cloud call), or pin one provider and read its policy.
- Review the README's privacy wording once decided, so it says exactly what leaves the robot.
- Decision (2026-11-04): documented and accepted for now. Revisit before any public release or wider use.

### Console step 9 (2026-11-04)
- Step 10 (contacts): the real group list has 89 member entries, 65 of them Signal UUIDs and 24 phone numbers. Names are known only for contacts in the contact list, and only a few of those carry a UUID, so most members cannot be named automatically. To be designed next.
- Tried in a browser on 2026-11-04 on a copy of the database with the real Signal group list: adding a group and removing it worked, by the author's report. Not individually confirmed: rename, deactivate and activate, the wrong-word and wrong-password refusals, and that the robot picks up group changes on its next check without a restart.
- Possible race: a message arriving while its group is being removed.

### Console step 10 (2026-11-04)
- Decision: adding a contact needs no extra password (the author's choice). Revisit if the console is ever reachable by anyone else.
- Limit: a contact who hides their number from group members may arrive as an ID only and be ignored as an unknown sender. A second contact row holding the ID would fix it, but it needs the ID, which only some contacts have.
- Tried in a browser on 2026-11-04 on a copy of the database with the real Signal contact list, by the author's report (add, rename, remove). Not individually confirmed: the refusals, and that the robot picks up contact changes on its next check without a restart.

### Console step 11 (2026-11-04)
- Log retention: both logs only grow, but slowly: on 2026-11-04 the audit log had 132 rows since 25 September and the activity log 10 since 28 October. Not urgent. Decide later how long to keep entries and how to trim them safely; the console deliberately cannot delete them.
- The mask on the Logs page is a safety net. If a real log line ever shows a number or an ID after masking, fix the code that wrote it.
- Tried in a browser on 2026-11-04 on a copy of the database with the real logs, by the author's report: it looked right, and no full numbers or IDs were seen.

### Security review (2026-11-04, first pass)
- See [security-review.md](reference/security-review.md). To check: the programs behind ports 8443 and 33785, whether the daemon on port 8000 asks for a login, SSH password logins and any firewall rules, a vulnerability scan of the Python packages.
- Regular database backup (daily, keep 14, owner-only). The Signal keys and the audio are deliberately not part of it.
- The console's certificate expires on 4 November 2027. Renew it with `python3 console/manage.py make-cert` and restart the service.
- The Pi's time zone is Europe/London. Harmless for the console (it has its own setting) but worth setting to Berlin for consistency.

### Publishing as a Reachy Mini app (2026-11-04)
- The author plans to publish Lola-Bla as a Reachy Mini app later. What that takes, and the decisions to make first, are in [publishing.md](architecture/publishing.md).
- Start at boot for the robot app is the daemon's `--startup-app` setting, once Lola-Bla is an installed app. No systemd service for it.
- Whether the dashboard's settings icon can point at an https console with a self-signed certificate. To test.
- Whether the background sync stops cleanly when the app is stopped. To check.

### Roadmap ideas (2026-11-04), to prioritise
- R1: Package Lola-Bla as a Reachy Mini app, which gives Run and Stop in Reachy Mini Control, the startup setting, install and remove. Large. See [publishing.md](architecture/publishing.md).
- R2: The console as the app's settings page (`custom_app_url`). Open: https with a self-signed certificate, and whether Reachy Mini Control opens it. Medium, with unknowns.
- R3: A toggle in the console for "start Lola-Bla when the robot wakes up", using the daemon's startup setting. Small, after checking that this daemon has the endpoint.
- R4: An interim launcher app for Run and Stop in Reachy Mini Control before R1. An experiment: can a second connection to the daemon coexist with the launcher's?
- R5: Measure the install size and the free space, and test two apps side by side. By the author's experience the robot has room for about two apps.
- R6: Decide about the version gap: SDK 1.11.0, daemon 1.10.0, documentation 1.13.
- R7: Start from the official `conversation` template, or keep Pollen's app and load the Lola-Bla tool and profile as external ones (can the two-line patch go away?).
- R8: Security: the daemon on port 8000 shows no login in the documentation, so nothing the console adds (such as the toggle in R3) may widen that.

### README and publishing ideas (2026-11-05)
- README: include the most important architecture diagrams (the current Mermaid versions, not the old PNGs in `docs/architecture/images/`).
- README: a video of Reachy with the app working.
- Safening of the app, before publishing: security hardening and child safety together. Starts from the security review and the final cybersec recheck at the end of the roadmap (ports, SSH, passwordless sudo, firewall, vulnerability scan, daemon API without a login, app lifecycle) and from "Deeper safety hardening" under General.
