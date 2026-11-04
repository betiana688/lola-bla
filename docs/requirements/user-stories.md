# User stories

| Story | Status |
|---|---|
| 1 — Reading messages | ✅ Complete |
| 2 — Replying to messages | ✅ Complete |
| 3 — Configuring the app | 🔨 In progress: sign-in, password, Signal linking and unlinking are built; groups, contacts and logs are next |
| 4 — Performance, security, privacy | ✅ Built and tested. Story 4c is only partly verified: the cloud services' data policies were read on 2026-11-04, and nothing published could be found for the live conversation (see the [cloud privacy check](../reference/cloud-privacy-check.md)) |

## Story 1: Reading messages

As Lola, I want Reachy to read out audio messages sent to Signal upon request, because I'm too young to read or write.

1. When checking messages, Reachy asks which group to check.
2. A message counts as new based on whether Reachy has played it, not Signal's read status.
3. Within the chosen group, three ways to select which messages play:
   - All new messages, in order, announcing the sender before each
   - By sender: only messages from a specific person in the group
   - By timestamp: only messages from a given time range
4. While playing, it's possible to stop and later continue from the last pause point.
5. If the selection yields no messages, Reachy says so.

## Story 2: Replying to messages

As Lola, I want Reachy to help me reply to audio messages upon request and automatically send them to the right group in Signal, because I'm too young to read or write.

1. When sending a message, Reachy asks which group to send to.
2. Recording supports pause and resume.
3. When recording is stopped: stop and replay, stop and send, or stop and delete. Replay loops back to the same choice.
4. Before sending, Reachy confirms which group it's about to send to.
5. If sending fails, Reachy reports the failure, never silently.

## Story 3: Configuring the app

As Betiana, I want to configure the app, because I want to make sure who can interact with Lola.

### Signing in

1. One console user per Signal account (1:1 for now), signing in with credentials over HTTPS (a self-signed certificate: the browser warns once).
2. The first user is created on the Pi itself, not through an open web page, and can be created before the Signal account is linked (fresh install).
3. The user can change their password, entering the current one first. Changing it ends all other sign-ins. A forgotten password is reset with a command on the Pi; a one-time code through Signal comes later.
4. Repeated failed sign-ins lock the login: 5 wrong passwords in a row lock it for 15 minutes. Wrong current passwords on the change-password page count too. Resetting the password on the Pi clears the lock.
5. Passwords are never stored or shown in readable form. The minimum length is 5 characters, chosen deliberately; the lockout carries the protection. Password fields have a Show/Hide button.

### Linking the Signal account

6. The user can link the robot's Signal device (named `reachy-mini`) to their account from the console by scanning a QR code with their phone, and can see whether it is linked. Linking is offered only when the Signal API has no account registered. If the scan is a different Signal account than the one the groups belong to, nothing is recorded and the page says so.
7. The user can unlink from the console. It needs a confirmation word and the password. The robot is marked unlinked first, so Reachy stops using the account and says so at once; then the console unregisters the number (never deleting the Signal account) and deletes the app's local Signal data. It then tells the user to remove the device in Signal on their phone, because only the phone can revoke it, and says plainly that it cannot check this once the number is unregistered. If the device is removed on the phone first, the status page notices, and "Clean up" finishes the job. If a step fails, the robot stays marked unlinked and "Finish unlinking" offers the rest.
8. Nothing outside the Pi can reach the Signal API, and the console acts only through the linked device.

### Managing approvals

9. Add, deactivate, and remove approved groups.
10. Add, edit, and remove contacts within an approved group; removals take effect immediately.
11. Group and member identifiers come from Signal; only the spoken name is typed.
12. The audit log and activity log are viewable only when signed in, with failures highlighted.

### Audit

13. Every console action is audited and records who did it: sign-ins (successful and failed), sign-outs, password changes, and link/unlink.

### Designed to grow (not features yet)

14. Adding other sign-in methods (such as Keycloak) and several Signal accounts per user later must not need a redesign.

## Story 4a: Performance and personality

As Betiana, I want Lola-Bla to respond quickly and naturally, with a personality suited to Lola, so conversations with Reachy feel comfortable, warm, and age-appropriate rather than mechanical.

1. Reachy begins its spoken response within 2 seconds of the person finishing speaking (target); no worse than 4 seconds in any case.
2. Phrasing varies across interactions rather than repeating an identical fixed sentence for the same situation.
3. If any single operation will take longer than the response-time target (e.g. syncing messages from Signal), Reachy gives an audible acknowledgment rather than silence.
4. Tone and phrasing are age-appropriate for a young child: simple language, warm and encouraging, patient with unclear or repeated input, never sarcastic, curt, or condescending.
5. The personality stays consistent across interactions, recognizably "itself" each time.
6. Content safety: Reachy never introduces or engages with frightening, violent, sexual, or otherwise mature content, and responds gently and safely if Lola brings up something upsetting or unclear.

## Story 4b: Security (access control)

As Betiana, I want to be the only person who can access sensitive data in this system, so Lola's information stays protected no matter where that data lives.

1. Only Betiana can access sensitive data (Signal account/credentials, contacts, groups, message content, logs), whether stored locally or processed by any third-party service the app uses.
2. No one else has this access by default; adding another authorized person (e.g. a partner) later is an explicit, deliberate action (backlog).
3. Any third-party service only sees the minimum needed for the specific request (e.g. a cloud LLM sees the current turn's text, not the full contact list or message archive).

## Story 4c: Data privacy

As Betiana, I want confidence that sensitive data isn't exposed to anyone beyond me, wherever it's processed, and I want visibility into what has accessed it.

1. Any third-party service that processes sensitive data (including audio) must not retain, share, or use it beyond fulfilling the immediate request: no training on it, no human review, no other customer or user ever able to access it.
2. Data sent to any external service goes through Betiana's own account/credentials, never a shared or public endpoint.
3. Before relying on any provider, its actual data-retention/training policy is checked and confirmed, not assumed.
4. An audit trail records access to where sensitive data is stored (database, contacts, logs, audio recordings). The exact mechanism is an implementation decision.
5. The audit trail is itself sensitive data, subject to Story 4b's access-control rule.

**Story 4c status (2026-11-04, researched).** Only partly verified. The messaging assistant: Hugging Face says it does not train on user data and does not store the request or response when routing, and that each downstream provider's own policy applies; the provider is not pinned, so its policy is unknown. The live conversation (Pollen's hosted real-time server, which hears the child's voice): no statement on retention, training or human review was found, and it is a shared hosted server, so item 2 is not met either, in this reading. Details and sources: [cloud privacy check](../reference/cloud-privacy-check.md).
