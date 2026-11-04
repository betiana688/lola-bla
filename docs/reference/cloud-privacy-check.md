# Cloud privacy check (Story 4c)

> **If you want to build this for a child, read this page first.** The author knows about the gaps below and has accepted them for now. You may decide differently.

Checked on 2026-11-04 from public pages only. Nothing was confirmed with the providers themselves, so this is a reading of what they publish, not a guarantee.

## What goes to the cloud

| What | Where | What it contains |
|---|---|---|
| The live conversation | Pollen's hosted real-time voice server (the app's default "deployed" mode, reached through a Hugging Face Space) | Everything the microphone hears while the app runs, except while a recording is made, and Reachy's spoken answers. Starting a session also reports the Hugging Face login saved on the robot and the robot's hardware ID |
| The messaging assistant | Hugging Face Inference Providers, then one downstream provider | Only the short task text the live agent writes, such as "check for new messages", sometimes with a group or sender name. Never audio, phone numbers or message content |

The recordings of messages, the database and the contacts never go to either service. In testing, the live conversation also transcribed speech that was not meant for it (a parent talking to the child nearby), because the microphone stays open while the app runs.

## What the services say

**Hugging Face Inference Providers** (the messaging assistant). Hugging Face says it does not store user data for training, does not store the request or response when routing, and keeps debugging logs for up to 30 days without user data or tokens. It also says each downstream provider's own data policy applies. The code names no provider, so the request goes to the first available provider in the account's preference order. Which provider serves the assistant is therefore not pinned, and its policy is not known.

**Pollen's hosted real-time server** (the live conversation). The app's README describes the default as the built-in Hugging Face server, reached through an app-managed Space proxy, needing no API key, and says nothing about retention, training or human review. Pollen's July 2026 blog post says this backend is Hugging Face's own open real-time voice engine, the same one used across their fleet, and that running it yourself costs only electricity. Hugging Face's May 2026 blog post says that until then audio had to be sent to a server, and lists privacy (audio never leaves your network) as the first reason to run your own. There are general statements that the robot sends no data to Pollen or Hugging Face unless cloud services are configured, but they are not a retention policy for this service. The proxy Space's own page could not be opened.

## Verdict against Story 4c

| Item | Messaging assistant | Live conversation |
|---|---|---|
| 1. No retention, training or human review beyond the request | Partly: Hugging Face's layer says so; the downstream provider is unknown, and human review is not mentioned | Not verified: nothing published was found |
| 2. Own account or credentials, never a shared endpoint | Met: its own token | Not met, in this reading: it is Pollen's shared hosted server |
| 3. The policy was actually checked | Partly | Not met |

## Ways to close the gap

1. Ask in writing. Pollen (contact@pollen-robotics.com, from its legal notice) and Hugging Face (privacy@huggingface.co, named on a Hugging Face privacy page) can be asked for retention, training and human-review statements for the hosted real-time server.
2. Run the real-time engine at home. The app supports it (`HF_REALTIME_CONNECTION_MODE=local`, with Hugging Face's open `speech-to-speech` project), and Hugging Face says the audio then never leaves your network. It needs a computer at home; Hugging Face's examples are an Apple Silicon Mac or a PC with a GPU. The Raspberry Pi in the robot is unlikely to be enough (our assessment, not from the source).
3. For the messaging assistant: use the local keyword rules only, so no cloud call is made, or pin one provider and read its policy.

## Sources

- [Hugging Face Inference Providers: security and compliance](https://huggingface.co/docs/inference-providers/security)
- [Hugging Face Inference Providers: provider selection](https://huggingface.co/docs/inference-providers/main/guides/first-api-call)
- [Pollen's conversation app README](https://github.com/pollen-robotics/reachy_mini_conversation_app)
- [Hugging Face blog: Reachy Mini goes fully local](https://huggingface.co/blog/local-reachy-mini-conversation)
- [Pollen blog: Reachy Mini talks with an open realtime voice](https://pollen-robotics.com/reachy-mini/blog/open-realtime-voice/)
- [Hugging Face blog: Reachy Mini announcement](https://huggingface.co/blog/reachy-mini)
