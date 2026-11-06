# Reachy Mini app proof of concept (2026-11-05)

Why: learn how the robot's app system really behaves, with a harmless stand-in app named `lola_bla` that moves nothing, plays nothing and only writes lines to `~/lola-poc.log`, before packaging the real app (R1). Nothing of the robot service's own environment (`/venvs/mini_daemon`) was touched; it was checked before and after.

## What we learned

- **Create and check:** the official `reachy-mini-app-assistant create` and `check` (use the copy in the daemon environment so the template matches the daemon). `check` test-installs the app in a throwaway environment, about 3.5 minutes on the Pi.
- **Install locally:** the robot service refuses `source_kind: local` (only Hugging Face apps install through its API). The manual route, as in the Pollen docs for offline Wireless units: create `/venvs/apps_venv` with the daemon's Python, install `reachy-mini==<daemon version>` and then the app with `uv pip install`. The apps environment took 406 MB and about 2 minutes; free disk went from 1.9 GB to 1.4 GB (90% used).
- **SDK version:** the apps environment is pinned to the daemon's version (1.10.0) so a failing test cannot be a version mismatch. Upgrading both together is R6.
- **Discovery:** the service lists the app immediately (entry point group `reachy_mini_apps`), no restart. App name, package name and entry point name must be identical (`lola_bla`).
- **Start and stop:** about 3 s from start to running; the app logs its first line about 2 s later. Stop takes about 2 s: the service sends SIGINT (Ctrl+C); see 'Later findings' below for what that means for cleanup. After every stop the service returns the robot to its zero position (the head moves). Only one app runs at a time.
- **Startup app:** the Wireless robot always boots asleep, and the service never starts an app at power-on. The startup app (the console switch) is launched by the first wake-up, or by touching an antenna: a watcher notices an antenna pushed about 14 degrees or more, wakes the robot and starts the app, about 2 s later, without the Reachy Mini Control app. Decision: use only this official route (no custom power-on helper, to avoid compatibility problems after updates).
- **Noise to review in the privacy and security check:** the service retries its "Central Relay" connection every minute ("Authentication failed") and the TURN credentials request every 30 s (the certificate of turn.fastrtc.org has expired). These are Pollen's remote-access features, not ours.

## Remove the POC

Stop the app, remove `lola_bla` through the service (`POST /api/apps/remove/lola_bla`), then delete `/venvs/apps_venv` only if nothing else is installed, plus `~/lola-poc` and `~/lola-poc.log`.

## Later findings (2026-11-05, evening)

- **Stopping is Ctrl+C.** The service sends SIGINT; in the main thread this raises `KeyboardInterrupt` inside `run()`, and the template's `__main__` block catches it and calls `app.stop()` afterwards. So `stop_event` is set only after `run()` was already unwound. All cleanup (audio, Signal, the console) must sit in `try/finally`, not after a `while not stop_event` loop. Evidence: "serve() returned" was never logged, "run() is ending" (from the `finally`) always was.
- **The console runs inside an app.** `server.serve(stop_event, ...)` was ready about 1 s after the start and answered like the normal console. On stop, both servers (console and standard settings page) logged a graceful shutdown within the same second. The apps environment needed one extra package for the console: `cryptography` (with `cffi`, `pycparser`); `starlette`, `uvicorn`, `jinja2` and `python-multipart` were already there. The proof of concept ran the console on a copy of the database, with Signal in read-only mode (`LOLA_SIGNAL_READONLY=1`). The service accepted `custom_app_url = "https://0.0.0.0:9444"`.
- **Reachy Mini Control v0.9.34 (desktop) stops a locally installed app about 62 s after it starts.** It happened every time (6 runs), whoever started the app (Control, antenna touch, API), with no settings page, with an HTTPS page, with an HTTP page, and with or without gentle robot movement. Control only polls `/api/daemon/status` every 5 s and never touches the app's ports; the stop request comes from the computer. With Control closed an app ran for minutes. Nothing found in the docs, Control's settings have no inactivity or sleep timer, and the 0.9.38 release notes only add a skippable daemon update prompt. Not understood; retest after updating the robot and Control together (R6). Lola's use does not need Control.
- **Control's Settings page:** System Update offers the robot software 1.10.0 to 1.14.0 (R6). "Reset Apps Cache" uninstalls all apps. "Clear HuggingFace Cache" removes cached models (candidate for R5, check what first). "Share anonymous usage data" is on (privacy check).
- **Service log noise:** Hugging Face app listing fails with 401 (stored token), the Central Relay fails every minute, TURN credentials fail every 30 s (expired certificate on turn.fastrtc.org).
- **The POC was closed on 2026-11-05:** switch turned off in the console, app removed through the service (`POST /api/apps/remove/lola_bla`), database copy and log deleted. The apps environment was kept for the real app.

## Root cause of the 60 s stop (2026-11-06)

Reachy Mini Control (0.9.34 and 0.9.38) stops an app when it cannot reach the app's web address
(`custom_app_url`). After the start, Control probes the address; if no probe succeeds within about 60 s it
calls `POST /api/apps/stop-current-app` (reachy-mini-desktop-app issue #272, PR #316 about malformed URLs).

Evidence (daemon 1.14.0, Control 0.9.38):
- https self-signed address (`https://reachy-mini.local:9443/`): stopped at exactly 60 s, every time.
- No address (POC phase A) and `https://0.0.0.0:9444` (phase B1/B2): stopped.
- Plain-http landing page answering HEAD and GET with 200, no redirect (`http://0.0.0.0:9080/`): ran 4 min
  when started from Control. Control's probe arrived 5 s after the start (1 HEAD, 2 GET), then stopped probing.
- Started from the robot with Control closed: never stopped (6 min, no request from other computers).

Not explained: phase B3 (`http://0.0.0.0:8042`, the SDK's own page) was also stopped. Possibly that page does
not answer HEAD with 200. Untested. Control's source was not read.

Decision: `lola_bla` keeps a tiny landing page (`app/src/lola_bla/landing.py`, port 9080, `LOLA_LANDING_PORT`):
static, no data, no login, link to the console. Remove it when Control no longer stops apps with an
unreachable address (check issue #272 / PR #316). Rule for the family: Control stays closed anyway.
Bug report filed with Pollen on 2026-11-06.

### Why the landing page is plain http (decision 2026-11-06)

Normally http is not acceptable; here it is a deliberate, temporary exception:
- The page is static: no login, form, cookie, message or name. Nothing to read or steal.
- Only risk: someone inside the home network alters the page (e.g. swaps the console link). That person could
  attack the console directly anyway, and the family does not use this page (Control stays closed).
- All real content (Signal, login) stays on the https console (9443). The daemon API (8000) is plain http too.
- An https address with a self-signed certificate was stopped by Control; a trusted certificate is not possible for `.local`.
- Reachable only on the home network (router firewall, to be confirmed in the privacy recheck). Exists only while the app runs.
- Console link on the page kept on purpose (Control's "Open" button leads to the console).
Revisit when Control no longer stops apps with an unreachable address (#272).

## Acceptance tests (2026-11-06)
- Test 7 (startup switch + antenna touch, Control closed): app stayed off after daemon restart, started ~3 s after touch, alive 6 min, console and landing page answered, no other computer connected. Lola profile active, robot spoke as Lola, movement OK. Robot could not describe what is in front of it (consistent with --no-camera; verify with script 52).
- Restart test (full OS reboot): PASS (app off until touch, then alive 2 min).

### Console link from Control (2026-11-06)

Clicking the landing page link showed "reachy-mini.local refused to connect" (Control panel and normal Chrome).
`https://<robot IP>:9443/` works. Cause (theory confirmed by the IP test): the console listens on IPv4 only
(0.0.0.0) while the PC resolves reachy-mini.local to IPv6. Control reaches the landing page by IP.
Separate on purpose: the console refuses to be shown inside another page (frame-ancestors 'none', X-Frame-Options DENY).
Fix: the landing page builds the console link from the Host header the viewer used (validated, fallback
reachy-mini.local), opens it in a new tab and prints the address as text. Open: console on IPv6 so that the name
works (needs a router check: FRITZ!Box blocks inbound IPv6 by default, to be confirmed in the privacy recheck).
