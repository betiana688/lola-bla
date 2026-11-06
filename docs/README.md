# Documentation

## Project

- [Development plan](development-plan.md): purpose, stories, how it was built, status
- [Backlog](backlog.md)
- [SBOM](sbom.md): software bill of materials

## Requirements

- [User stories](requirements/user-stories.md): Stories 1–4 with acceptance criteria
- [Emotions mapping](requirements/emotions-mapping.md): Reachy's reactions per conversation state

## Architecture

- [Overview](architecture/overview.md): system, two agents, mic handoff, privacy rules, decisions
- [Conversation app](architecture/conversation-app.md): check messages, Signal sync, states, module diagrams
- [Configuration console](architecture/console.md): the design (login, password recovery, Signal link and unlink) and what is built so far
- [Console redesign: two doors](architecture/console-redesign.md): decision and spec for the light page in Control and the full console in a browser
- [Data model](architecture/data-model.md)
- [Publishing as a Reachy Mini app](architecture/publishing.md): how apps work, what differs today, switching to another app
- [How the Pi, the repo and GitHub connect](architecture/pi-repo-connection.md): where files and data live, and what is pushed
- [How the Pi, the repo and GitHub connect](architecture/pi-repo-connection.md): where files and data live, and what is pushed

## Reference

- [Database](reference/database.md): `sqlite3` commands for groups, contacts, messages, logs
- [signal-cli-rest-api](reference/signal-cli-rest-api.md): endpoints for linking, receiving, sending, and what our own tests showed
- [Cloud privacy check](reference/cloud-privacy-check.md): what the two cloud services publish about data (Story 4c)
- [Security review](reference/security-review.md): what is reachable, what is protected, what is accepted, what is still to check

## Brand

- [Brand](brand/README.md): the mark, app icon, colours, type, voice and ready-made posters

## Agent profile

- [profiles/lola/profile.md](../profiles/lola/profile.md): personality, safety rules, voice, enabled tools
