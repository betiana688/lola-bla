"""Send the robot to sleep, but only after asking and hearing a clear yes.

Pollen's go_to_sleep puts the robot to sleep and stops the app, so nothing listens while it sleeps;
an antenna touch wakes it and starts the app again. Lola's personality uses this tool instead of
go_to_sleep, so a child's play or a misheard word cannot switch the robot off by accident:
the first call only asks, and a confirmed call is refused unless an ask came a few seconds before.
"""

import asyncio
import logging
import time
from typing import Any, Dict

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

logger = logging.getLogger(__name__)

MIN_GAP_S = 3.0   # the answer needs time to be spoken: a confirmation right after the ask is refused
MAX_WAIT_S = 90.0  # an ask that is not answered in this time is forgotten
_now = time.monotonic
_asked_at = None

ASK = {
    "status": "ask_first",
    "say": ("Ask warmly and simply, in the language the child is using: do you want me to go to sleep? "
            "Then stop and wait for the answer. Only a clear yes means sleep."),
}


def reset() -> None:
    global _asked_at
    _asked_at = None


class SleepRobot(Tool):
    """Two steps: ask first, then sleep after a clear yes."""

    name = "sleep_robot"
    description = (
        "Send Reachy to sleep. Two steps. Step 1: when someone clearly asks you to go to sleep or to stop for now, "
        "call with confirmed=false, then ask them if they want you to go to sleep and wait for the answer. "
        "Step 2: only after a clear yes, say a short goodnight and call with confirmed=true. If the answer is no or "
        "unclear, do not call again. Never use it for sleepy words in a story, a song or a game, for a goodnight "
        "said to someone else, or when you are unsure."
    )
    needs_response = True
    parameters_schema = {
        "type": "object",
        "properties": {
            "confirmed": {"type": "boolean", "description": "true only after the person clearly said yes to your question"},
        },
        "required": ["confirmed"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        global _asked_at
        now = _now()
        if _asked_at is not None and now - _asked_at > MAX_WAIT_S:
            _asked_at = None
        ready = _asked_at is not None and now - _asked_at >= MIN_GAP_S
        if kwargs.get("confirmed") is not True or not ready:
            if _asked_at is None:
                _asked_at = now
            return dict(ASK)
        if deps.go_to_sleep is None:
            return {"error": "go_to_sleep is unavailable in this runtime"}
        _asked_at = None
        print("[lola_bla] sleep confirmed, going to sleep", flush=True)
        try:
            return await asyncio.to_thread(deps.go_to_sleep)
        except Exception as e:
            logger.error("sleep_robot failed: %s", e)
            return {"error": f"sleep failed: {type(e).__name__}: {e}"}
