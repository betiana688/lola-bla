"""Background receive for Lola-Bla. Runs inside the conversation app (as a daemon
thread) and pulls new Signal messages into the database every couple of minutes, so
"check my messages" reads the database instead of waiting on Signal, and the linked
device never sits idle. It stops when the app stops."""

import logging
import os
import threading
import time

import messaging_executor

logger = logging.getLogger(__name__)

INTERVAL_S = 120
STARTUP_DELAY_S = 15  # let the app finish starting first

_started = False
_start_lock = threading.Lock()


def start() -> bool:
    """Start the background thread once. Safe to call repeatedly. Set
    LOLA_NO_BACKGROUND_SYNC=1 to disable it (used by offline tests)."""
    global _started
    with _start_lock:
        if _started or os.environ.get("LOLA_NO_BACKGROUND_SYNC"):
            return False
        _started = True
    threading.Thread(target=_run, name="lola-background-sync", daemon=True).start()
    logger.info("Background sync enabled (every %d s)", INTERVAL_S)
    return True


def _run() -> None:
    time.sleep(STARTUP_DELAY_S)
    failing = False
    while True:
        try:
            status, error = messaging_executor.sync_now()
            logger.info("Background sync: %s", status)
            if status == "failed" and not failing:
                failing = True
                messaging_executor.log_event(
                    "background_sync_failed", "failed",
                    f"Could not check Signal in the background ({error}); will keep trying")
            elif status != "failed" and failing:
                failing = False
                messaging_executor.log_event(
                    "background_sync_recovered", "ok", "Background check of Signal works again")
        except Exception:
            logger.exception("Background sync loop error")
        time.sleep(INTERVAL_S)
