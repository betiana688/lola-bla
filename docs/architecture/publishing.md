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

## Turning the app on and off, and starting it at boot (second look, same day)

Pollen's documentation (the `main` version, newer than the SDK on the author's robot) describes both a visual and a command-line way, for installed apps:

- Reachy Mini Control (the desktop and phone app) has an Applications tab where apps are installed, started and stopped. It opens an app's settings page (`custom_app_url`) as soon as that page answers.
- The daemon's REST API on port 8000 does the same by command: install, start, stop, list the installed apps, show which app runs now, remove and update.
- Starting at wake-up is a setting that can be read, set and cleared at any time (`GET` and `PUT /api/apps/startup-app`). The app starts after wake-up, or when an antenna is touched on a sleeping robot, and only when no other app holds the app slot. Pointing it at another app, or clearing it, is the configurable boot start.
- For runtime configuration such as keys and server addresses, the documentation recommends the app's own web page, which is what the console is. The app's process inherits the daemon's environment and there is no other way to inject settings.
- There is an official `conversation` template for `reachy-mini-app-assistant create`, with audio, LLM tools and motion built in. It is an alternative to forking Pollen's conversation app.
- Pollen's conversation app can load profiles and tools from outside its own code (its README describes an external profiles folder, an external tools folder and an autoload switch), so Lola-Bla's tool and profile might live outside Pollen's package. The two-line patch is not covered by this. To check.

What follows from it:

1. No systemd service for the robot app. Packaging it gives Run and Stop in Reachy Mini Control and the startup setting for free.
2. The console becomes the app's settings page. It could carry a toggle for "start Lola-Bla when the robot wakes up" that calls the daemon's startup setting, with no system rights. To check first: that the daemon on this robot (SDK 1.11.0, daemon 1.10.0) has these endpoints, because the documentation describes newer versions.
3. Open question: the framework serves a settings page over plain HTTP on the home network, while the console needs HTTPS because of its password sign-in. Whether `custom_app_url` can point at an https address with a self-signed certificate, and whether Reachy Mini Control opens such a page, is to test. Until then the console's own address stays the way in.
4. Until the app is packaged there is no visual on/off for Lola-Bla. The stopgap is the commands in `console/install_service.sh` and the steps above. A middle option is a small launcher app that starts Lola-Bla from its own environment and stops it on the `stop_event`. It is an experiment: it is not known whether the daemon allows a second connection to the robot while the launcher holds one.
5. Space on the robot is tight. By the author's experience it has room for about two apps. Keeping Pollen's conversation app installed next to Lola-Bla is treated as an edge case. A fork would double its code, while a dependency shares one copy.

## Status on 2026-11-06

- The package `lola_bla` has the right name, class and entry point. Pollen's checker (`reachy-mini-app-assistant check`) reports one thing missing: the Space's `index.html` landing page.
- **Known gap, accepted for now:** `reachy-mini-conversation-app` and `lola-console` are not published on a package index, so the store cannot install Lola-Bla on someone else's robot yet. Today it installs from this repository on the author's robot only.
- **Known gap, accepted for now:** Lola-Bla needs a small patch on Pollen's conversation app (`app/patches/`). It is applied by `app/install.sh`, not by the store. Options when this is tackled: get the change accepted upstream, or fork.
- Decisions made: Apache-2.0 license; the cloud assistant stays optional (the local rules work without an account); the first release will be private, to test the whole path before anyone else sees it.
