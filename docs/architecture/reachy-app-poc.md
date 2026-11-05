# Reachy Mini app proof of concept (2026-11-05)

Why: learn how the robot's app system really behaves, with a harmless stand-in app named `lola_bla` that moves nothing, plays nothing and only writes lines to `~/lola-poc.log`, before packaging the real app (R1). Nothing of the robot service's own environment (`/venvs/mini_daemon`) was touched; it was checked before and after.

## What we learned

- **Create and check:** the official `reachy-mini-app-assistant create` and `check` (use the copy in the daemon environment so the template matches the daemon). `check` test-installs the app in a throwaway environment, about 3.5 minutes on the Pi.
- **Install locally:** the robot service refuses `source_kind: local` (only Hugging Face apps install through its API). The manual route, as in the Pollen docs for offline Wireless units: create `/venvs/apps_venv` with the daemon's Python, install `reachy-mini==<daemon version>` and then the app with `uv pip install`. The apps environment took 406 MB and about 2 minutes; free disk went from 1.9 GB to 1.4 GB (90% used).
- **SDK version:** the apps environment is pinned to the daemon's version (1.10.0) so a failing test cannot be a version mismatch. Upgrading both together is R6.
- **Discovery:** the service lists the app immediately (entry point group `reachy_mini_apps`), no restart. App name, package name and entry point name must be identical (`lola_bla`).
- **Start and stop:** about 3 s from start to running; the app logs its first line about 2 s later. Stop takes about 2 s: the service sends SIGINT, the SDK sets `stop_event`, the app leaves cleanly, no process is left. After every stop the service returns the robot to its zero position (the head moves). Only one app runs at a time.
- **Startup app:** the Wireless robot always boots asleep, and the service never starts an app at power-on. The startup app (the console switch) is launched by the first wake-up, or by touching an antenna: a watcher notices an antenna pushed about 14 degrees or more, wakes the robot and starts the app, about 2 s later, without the Reachy Mini Control app. Decision: use only this official route (no custom power-on helper, to avoid compatibility problems after updates).
- **Noise to review in the privacy and security check:** the service retries its "Central Relay" connection every minute ("Authentication failed") and the TURN credentials request every 30 s (the certificate of turn.fastrtc.org has expired). These are Pollen's remote-access features, not ours.

## Remove the POC

Stop the app, remove `lola_bla` through the service (`POST /api/apps/remove/lola_bla`), then delete `/venvs/apps_venv` only if nothing else is installed, plus `~/lola-poc` and `~/lola-poc.log`.
