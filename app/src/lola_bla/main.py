"""Lola-Bla: family voice messages for the Reachy Mini.

Runs Pollen's conversation app with the Lola profile and the family console
side by side. When the app is stopped, both shut down.
"""

import os
import sys
import threading

from reachy_mini import ReachyMini
from reachy_mini_conversation_app.main import ReachyMiniConversationApp

PROFILE = "lola"
ROBOT_ARGS = ["--no-camera"]  # privacy by design: no camera in Lola's room


def say(text: str) -> None:
    print(f"[lola_bla] {text}", flush=True)


def prepare_environment() -> None:
    """Set the profile and the command line that the conversation app reads."""
    os.environ["REACHY_MINI_CUSTOM_PROFILE"] = PROFILE
    sys.argv = [sys.argv[0], *ROBOT_ARGS]


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


class LolaBla(ReachyMiniConversationApp):
    """Lola-Bla as a Reachy Mini app."""

    custom_app_url = "https://reachy-mini.local:9443/"
    dont_start_webserver = True  # no settings page without a login

    def run(self, reachy_mini: ReachyMini, stop_event: threading.Event) -> None:
        prepare_environment()
        console = start_console(stop_event)
        try:
            super().run(reachy_mini, stop_event)
        finally:
            stop_event.set()
            console.join(timeout=15)
            say("stopped")


if __name__ == "__main__":
    app = LolaBla()
    try:
        app.wrapped_run()
    except KeyboardInterrupt:
        app.stop()
