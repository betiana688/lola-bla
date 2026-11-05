# Publishing as a Reachy Mini app

Notes from 2026-11-04, written while deciding how the console should start. Nothing here is built yet. The facts come from Pollen's and Hugging Face's published documentation (sources at the end), not from trying it on the robot.

## How Reachy Mini apps work

- An app is a Python package with a class that extends `ReachyMiniApp` and a `run(reachy_mini, stop_event)` method. It is published as a Hugging Face Space whose README carries the tag `reachy_mini_python_app`, and it has an entry point in `pyproject.toml`. The `reachy-mini-app-assistant` tool creates and publishes this structure.
- The robot's daemon manages the lifecycle. When asked (from the dashboard or its REST API), it starts the app as a Python subprocess, hands it a connected robot, and ends it through the `stop_event`. The app does not manage its own hardware connections.
- Only one app runs at a time. Starting another one needs the current one stopped first.
- On the wireless robot, apps are installed into a shared virtual environment, `/venvs/apps_venv/`.
- An app can have a settings page: it sets `custom_app_url`, serves a `static/` folder with a small web server, and the dashboard shows a settings icon (the documentation's example uses port 8042).
- Starting at boot or wake-up is a daemon option, `--startup-app <name>`, which makes one installed app the default experience on wake-up or antenna touch. The daemon listens on port 8000 (REST API and dashboard).

## Where Lola-Bla differs today

| Today | As a published app |
|---|---|
| Pollen's app is a git clone pinned to one commit, with a two-line patch | Its own package: a fork of Pollen's conversation app (Apache-2.0), or a dependency plus a change accepted upstream |
| Started by hand from a separate Python environment | Installed in the shared apps environment and started by the daemon |
| Our files are linked into the clone | One installable package |
| The console is a separate program on port 9443, optionally a systemd service | Started by the app's `run()` and stopped by the `stop_event`, so removing the app removes the console. Announced with `custom_app_url` |
| Data and secrets live in the clone's `local_data` folder | In a folder outside the package, so removing the app never deletes the Signal keys |
| The Signal API is a Docker container that someone set up | A prerequisite the user sets up, or something a first-run step creates (Docker is on the robot image today) |
| The messaging assistant needs a Hugging Face token and credits | The local keyword rules should work without any account, with the cloud assistant optional |

## Decisions for later

1. **Fork or depend.** Forking is simplest, but it has to follow Pollen's updates. A dependency needs the two-line patch accepted upstream.
2. **The console inside the app.** Start it from `run()` in a thread, stop it with the `stop_event`. Open question: whether the dashboard's settings icon accepts an https address with a self-signed certificate. If not, the icon cannot point at the console, and users open its address by hand.
3. **The Signal API container.** Prerequisite with a setup guide, or created by the app. Either way the first-run flow starts at the console's Signal page.
4. **Data and uninstalling.** Removing the app keeps the data by default. A separate, documented purge removes it.
5. **Start at boot.** The daemon's `--startup-app` setting, once Lola-Bla is an installed app. No systemd service for the robot app, because the daemon already owns the hardware and allows one app at a time.
6. **The background sync** runs inside the app today. As an app it must stop when the `stop_event` is set. To check.
7. **The listing text** carries the privacy section from the README, so everyone sees it before installing.
8. **Before publishing:** remove `test_mic_handoff` from Lola's tools, and decide the Hugging Face credits question.

## Switching to a different app (today)

Lola-Bla is not a Reachy Mini app yet. It is started by hand, and the daemon does not know about it. To switch to another app:

1. Stop Lola-Bla (Ctrl+C in the terminal where it runs).
2. If the console runs as a service: `./console/install_service.sh --boot off` keeps it available but not at boot, `./console/install_service.sh --stop` stops it, and `./console/install_service.sh --remove` removes the service.
3. Start the other app from the robot's dashboard.

Your data stays where it is: the database, the audio, the Signal keys, the messaging token and the console's certificate. The Signal API container keeps running unless you stop it: `docker update --restart=no signal-api && docker stop signal-api`.

To remove everything for good, in this order: unlink from the console (so the robot stops using the account), remove `reachy-mini` under Linked devices in Signal on the phone, stop and delete the container (`docker rm signal-api`), then delete the folders `~/lola-bla-agents`, `~/.config/lola-bla` and `~/.local/share/signal-api`. Deleting the database and the audio is permanent.

## Sources

- [Reachy Mini documentation: building and publishing apps](https://huggingface.co/docs/reachy_mini/main/SDK/apps)
- [Seeed wiki: Reachy Mini apps](https://wiki.seeedstudio.com/reachymini_sdk_apps/)
- [Seeed wiki: development workflow for the wireless Reachy Mini](https://wiki.seeedstudio.com/reachymini_platforms_reachy_mini_development_workflow)
