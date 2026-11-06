"""Lola-Bla: family voice messages for the Reachy Mini.

Runs Pollen's conversation app with the Lola profile and the family console
side by side. When the app is stopped, both shut down.
"""

import sys
import threading
from pathlib import Path

from reachy_mini import ReachyMini
from reachy_mini_conversation_app import config as conv_config
from reachy_mini_conversation_app.main import ReachyMiniConversationApp

from lola_bla import landing

PROFILE = "lola"
ROBOT_ARGS = ["--no-camera"]  # privacy by design: no camera in Lola's room


class ProfileError(RuntimeError):
    """The Lola profile is not the active one. The app must not run with another personality."""


def say(text: str) -> None:
    print(f"[lola_bla] {text}", flush=True)


def prepare_environment() -> None:
    """Set the command line that the conversation app reads. The camera stays off."""
    sys.argv = [sys.argv[0], *ROBOT_ARGS]


def ensure_profile() -> None:
    """Make Lola's profile the active one, or refuse. A generic personality must never reach Lola."""
    conv_config.set_custom_profile(PROFILE)
    active = conv_config.config.REACHY_MINI_CUSTOM_PROFILE
    if active != PROFILE:
        raise ProfileError(f"active profile is {active!r}, expected {PROFILE!r}")
    profile_file = Path(conv_config.config.PROFILES_DIRECTORY) / PROFILE / "profile.md"
    if not profile_file.is_file():
        raise ProfileError(f"profile file not found: {profile_file}")
    say(f"profile {PROFILE} is active")


def start_console(stop_event: threading.Event) -> threading.Thread:
    """Start the family console in the background. It stops when stop_event is set."""

    def serve() -> None:
        try:
            from lola_console import server

            server.serve(stop_event, port=server.port_from_env(), on_ready=lambda: say("console is ready"))
        except Exception as e:  # the app must keep running without the console
            say(f"console is NOT running: {e}")

    thread = threading.Thread(target=serve, name="lola-console-runner", daemon=True)
    thread.start()
    return thread


def start_landing(stop_event: threading.Event) -> threading.Thread:
    """Start the plain-http landing page in the background. It stops when stop_event is set."""

    def serve() -> None:
        try:
            landing.serve(stop_event, on_ready=lambda port: say(f"landing page is ready on port {port}"))
        except Exception as e:  # the app must keep running without it
            say(f"landing page is NOT running: {e}")

    thread = threading.Thread(target=serve, name="lola-landing-runner", daemon=True)
    thread.start()
    return thread


class LolaBla(ReachyMiniConversationApp):
    """Lola-Bla as a Reachy Mini app."""

    custom_app_url = "http://0.0.0.0:9080/"
    dont_start_webserver = True  # no settings page without a login

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        prepare_environment()
        ensure_profile()  # raises before the console or the microphone start
        console = start_console(stop_event)
        page = start_landing(stop_event)
        try:
            super().run(reachy_mini, stop_event)
        finally:
            stop_event.set()
            console.join(timeout=15)
            page.join(timeout=10)
            say("stopped")


if __name__ == "__main__":
    app = LolaBla()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
