# Safe and private

I built this for my own young daughter, so these are the questions I asked first. Short answers, with links to the details.

## Who can talk to Lola?

Only people you approved, one by one. A Signal group must be approved, and each person in it must be approved too, and must be in your Signal contacts with a phone number. Everyone else is ignored. Lola always says which group a message came from.

## What stays on the robot?

- The **audio of every message** (the ones she plays and the ones you record)
- Your **contacts, groups and database**
- Your **Signal keys**

None of this is sent to the cloud services. They are told only the outcome of an action ("message sent", "two new messages from Grandma"). Keep backups private: they contain the Signal keys.

## What goes to the cloud?

- **The live conversation.** While the app runs, what the microphone hears goes to Pollen's hosted voice service, so she can answer quickly. That includes speech that is not meant for the robot, except while a message is being recorded. I could not find a published statement about how long that service keeps audio or whether anyone reviews it. When you send her to sleep, the app stops and nothing is sent.
- **The messaging assistant.** A short task text (sometimes a group or sender name) goes to Hugging Face's Inference service to decide what a request means. If it is not reachable, simple rules on the robot take over.

Details and sources: [cloud privacy check](../reference/cloud-privacy-check.md).

## Still improving

I keep a list of privacy improvements and work through it before anything is published as an app. If you find something I missed, please tell me privately: see [SECURITY.md](../../SECURITY.md).

## How the settings are protected

The settings page uses HTTPS and a password, locks after five wrong tries, asks for the password again for risky actions (removing a group, changing the start setting), writes every action to an audit log, and never shows a phone number in full. The page you see inside Reachy Mini Control has no login because it holds no private data: only the app name and whether Signal is linked, never the number.

## If you build this for a child

Decide for yourself. The privacy choices above are mine, and they may not be yours.

Next: [when something is off](troubleshooting.md).
