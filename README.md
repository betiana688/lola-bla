# Lola-Bla

A Reachy Mini robot that lets a young child hear and send voice messages to family abroad — safely, and entirely on her own.

## Why I built this

I grew up able to just pick up the phone and call my grandparents whenever I wanted to. As a foreigner raising my daughter in Germany, far from most of our family, I wanted her to have that same simple, direct connection — without needing to ask me to unlock my phone and dial every single time.

At the same time, she's a small child, and I wasn't willing to hand her open access to a messaging app or a phone. Lola-Bla is my answer to both: a robot she can just talk to, that reads her messages aloud and helps her record replies, while every piece of it is built so that only I can ever see or touch the sensitive parts — her contacts, her messages, who she's allowed to talk to.

This project was also my capstone during maternity leave — a hands-on way to actually understand, by building one myself, what a "multi-agent system" really means in practice, beyond the buzzword. (Worth being upfront: this specific app didn't *need* two agents — a single agent with more tools would have worked just as well, and been simpler. I built it with two deliberately, as a genuine multi-agent exercise, not because the task demanded it.)

## What it does

- **Reads messages aloud** — Reachy checks a small set of approved family Signal groups, announces who a message is from and when it arrived, and plays it.
- **Records and sends replies** — a clear start cue, records until she stops talking, a clear "done" cue, then lets her hear it back, send it, or try again before anything is sent.
- **Talks naturally** — real, warm, back-and-forth conversation, not a rigid command list. Responses are quick (typically under 2 seconds) and age-appropriate for a young child, with built-in guardrails to keep the conversation safe and always ready to point her to a parent for anything outside its scope.

## Architecture, and why it's safe

Two things happen in two different places, deliberately kept apart:

- **The conversation itself** — hearing the child, understanding her, speaking back — happens through a real-time cloud AI service. This is what makes it feel natural and fast.
- **Everything sensitive — the actual message content, contacts, who's allowed to talk to whom, and the message audio itself — never leaves the robot.** Recording, storage, and sending all happen locally. The cloud service is only ever told the *outcome* of an action ("message sent" / "here are 2 new messages from Grandma"), never given raw audio, names of specific people, or database access.

Concretely, the robot uses **two separate AI agents**: one handles the live conversation and personality; the other, invoked only internally, decides *what* the child is asking for and hands that decision to plain, local code that actually does it — record, check, or send. The two never talk to each other directly, and neither one is ever handed more information than it strictly needs to do its one job.

On top of that: only the family administrator (me) can access the underlying data or logs, no matter where they're stored; every access to sensitive data is recorded in an audit trail I can review; and being a member of a family Signal group isn't enough on its own to be trusted — every person has to be explicitly approved before their messages count.

## Status

- ✅ Reading messages
- ✅ Recording and sending replies
- ✅ Natural conversation, performance, and safety guardrails
- 🔜 **A web-based configuration console**, so approving groups/contacts and reviewing logs won't require touching a database by hand — currently managed manually as an interim step

## Running it

Requires a Reachy Mini Wireless, a linked Signal account, and a Hugging Face account.

```bash
# Project + venv
mkdir -p ~/lola-bla-agents && cd ~/lola-bla-agents
python3 -m venv venv && source venv/bin/activate

# The conversation engine (built on Pollen Robotics' open-source Reachy Mini app)
git clone https://github.com/pollen-robotics/reachy_mini_conversation_app.git
cd reachy_mini_conversation_app
pip install -e .

# Auth
hf auth login

# Local data
mkdir -p local_data
sqlite3 local_data/lola.db < local_data/schema.sql
chmod 700 local_data local_data/audio
chmod 600 local_data/lola.db local_data/messaging_agent.py local_data/messaging_executor.py
```

Set your own Signal number in `local_data/messaging_executor.py`, then register approved groups/contacts directly via `sqlite3` (a proper console is on the way — see Status above).

Run it:

```bash
REACHY_MINI_CUSTOM_PROFILE=lola reachy-mini-conversation-app --no-camera
```

## Known limitations

- No configuration console yet — approvals are managed by hand
- Fixed maximum recording length (30s), with automatic stop after ~5 seconds of silence
- A couple of small local patches to the underlying conversation engine aren't yet upstreamed

## Documentation

Everything else lives in [docs/](docs/README.md): user stories, architecture and diagrams, data model, development plan, SBOM, backlog and command references.

## Repository layout

```
app/              Conversation app code (messaging tool, agent, executor)
console/          Configuration console (Story 3)
profiles/lola/    The conversational agent's personality and safety profile
docs/             Requirements, architecture, references
```

## License

TBD.
