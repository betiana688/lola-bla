# Lola-Bla

A Reachy Mini robot that lets a young child hear and send voice messages to family abroad — safely, and entirely on her own.

## Why I built this

I grew up able to just pick up the phone and call my grandparents whenever I wanted to. As a foreigner raising my daughter in Germany, far from most of our family, I wanted her to have that same simple, direct connection — without needing to ask me to unlock my phone and dial every single time.

At the same time, she's a small child, and I wasn't willing to hand her open access to a messaging app or a phone. Lola-Bla is my answer to both: a robot she can just talk to, that reads her messages aloud and helps her record replies, while every piece of it is built so that only I can ever see or touch the sensitive parts — her contacts, her messages, who she's allowed to talk to.

This project was also my capstone during maternity leave — a hands-on way to actually understand, by building one myself, what a "multi-agent system" really means in practice, beyond the buzzword. (Worth being upfront: this specific app didn't *need* two agents — a single agent with more tools would have worked just as well, and been simpler. I built it with two deliberately, as a genuine multi-agent exercise, not because the task demanded it.)

## Built with Claude

I built this together with [Claude](https://claude.ai), Anthropic's AI assistant, and part of the point was to find out how far I could get working that way. Claude proposed the designs and wrote most of the code, tests and documentation. I made the decisions, ran everything on the robot, and tested it with a real phone, a real browser and real hardware.

How we worked, and what I learned:

- **Spec first, then build, then docs in the same step.** User stories and acceptance criteria came before any code. When I let the docs slip, they fell behind within days, so updating them with each step is now a rule.
- **Small steps, each verified.** Every piece was tested on its own (offline tests with fakes, then the real thing) before the next one was built on top.
- **The assistant makes mistakes, and the process catches them.** A security header made the console refuse every sign-in (found in a real browser, now pinned by a test). Asking for the group "Test" also played "Another test" (found in a live run). Messages were once marked as played when playback had failed. Nothing counted as done until it ran.
- **Safety by structure, not by promise.** Data and secrets live outside the repo so they cannot be committed by accident, a scan runs before every push, and the cloud AI only ever sees names, counts and timestamps.
- **It only knows what I show it.** Claude cannot see my screen or my robot. Everything it knew about what actually happened came from the output I pasted back, so those pastes were part of the engineering.

If you want to try this yourself: ask for the spec before the code, make it show its work, test on the real thing, and keep the docs moving with the code.

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
- 🔨 **A web-based configuration console**: signing in over HTTPS, changing the password and linking Signal are built; managing groups and contacts and viewing logs come next. Until then, approvals are managed by hand.

## Running it

Needs a Reachy Mini Wireless with its daemon running, a Signal account on your phone, Docker, `sox`, `ffmpeg`, `sqlite3` and a Hugging Face account. The install script has been tested in a scratch folder except for its Python-environment step, so treat a first install as a dry run.

### Install

```bash
git clone https://github.com/betiana688/lola-bla.git
cd lola-bla
./app/install.sh
```

The script clones Pollen's app at the commit we run, applies our two-line patch, links our files into it (one copy of each, in this repo), creates the database and sets up the Python environment.

### Then, by hand

1. Start the Signal API so that it listens on this machine only. We run version 0.100 (see `/v1/about`); pin the image to a version once you know which one works for you.
   ```bash
   docker run -d --name signal-api --restart=always -p 127.0.0.1:8080:8080 -v $HOME/.local/share/signal-api:/home/.local/share/signal-cli -e MODE=native bbernhard/signal-cli-rest-api
   ```
2. From the repo folder, create the console user and its certificate, then start the console, open `https://reachy-mini.local:9443/`, sign in, and link your Signal account on its Signal page (scan the QR code in Signal, under Linked devices):
   ```bash
   source ~/lola-bla-agents/venv/bin/activate
   python3 console/manage.py create-user
   python3 console/manage.py make-cert
   python3 console/run.py
   ```
3. Give the messaging assistant its own Hugging Face token, in a file only you can read, and log in to Hugging Face for the live conversation:
   ```bash
   read -rs -p "Token: " T; echo
   ( umask 177; printf '%s' "$T" > ~/lola-bla-agents/reachy_mini_conversation_app/local_data/hf_token ); unset T
   hf auth login
   ```
4. Add your approved groups and contacts. For now that is done with `sqlite3` (see [docs/reference/database.md](docs/reference/database.md)); the console pages for it are coming.
5. Start the app:
   ```bash
   cd ~/lola-bla-agents/reachy_mini_conversation_app
   REACHY_MINI_CUSTOM_PROFILE=lola reachy-mini-conversation-app --no-camera
   ```

## Known limitations

- The console cannot yet unlink Signal, manage groups and contacts, or show logs: approvals are still managed by hand
- The console password minimum is short on purpose (5 characters); the sign-in lockout (5 tries, 15 minutes) is the protection
- The messaging assistant needs Hugging Face credits; without them a simple local fallback keeps messaging working
- Fixed maximum recording length (30s), with automatic stop after ~5 seconds of silence
- Two small local patches to the underlying conversation engine are kept as a patch file (`app/patches`) and are not yet upstreamed

## Documentation

Everything else lives in [docs/](docs/README.md): user stories, architecture and diagrams, data model, development plan, SBOM, backlog and command references.

## Repository layout

```
app/              Conversation app code (messaging tool, agent, executor, schema)
console/          Configuration console (Story 3)
prototype/        First, fully local version (superseded, kept for reference)
profiles/lola/    The conversational agent's personality and safety profile
docs/             Requirements, architecture, references
```

## License

TBD.
