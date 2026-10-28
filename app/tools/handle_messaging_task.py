"""The tool the Conversational Agent calls. Delegates interpretation to the
Messaging Agent, and handles the pieces that need real hardware access:
recording, playback, and holding the just-recorded file between calls."""

import logging
import subprocess
import sys
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "local_data"))
import messaging_agent  # noqa: E402
import messaging_executor  # noqa: E402

logger = logging.getLogger(__name__)

RECORDING_PATH = Path("/tmp/lola_message_recording.wav")
SILENCE_THRESHOLD = "3%"
SILENCE_DURATION_S = "5.0"
MAX_RECORD_SECONDS = 30  # safety cap, in case silence is never detected

# Persists across tool calls within this one running app - not written to disk,
# so a crash/restart clears it (a half-finished recording shouldn't survive that).
_pending_recording: Optional[Dict[str, Any]] = None


def _match_group(group_name: Optional[str]):
    groups = messaging_executor.get_active_groups_list(accessed_by="messaging_agent")
    if not groups:
        return None
    if not group_name:
        return groups[0] if len(groups) == 1 else None
    for g in groups:
        if group_name.lower() in g["group_name"].lower():
            return g
    return None


def _play_beep(frequency_hz: int, duration_s: float = 0.15) -> None:
    """Short local tone - used as start/done cues so the child knows
    exactly when recording begins and ends."""
    subprocess.run([
        "sox", "-n", "-t", "alsa", "reachymini_audio_sink",
        "synth", str(duration_s), "sine", str(frequency_hz), "vol", "0.3"
    ], check=False)


def _record_message(deps: ToolDependencies) -> bool:
    """Mutes the live conversation, plays a start cue, records locally via
    the shared ALSA device with stop-on-silence, plays a done cue, unmutes.
    Returns True on success."""
    stream_manager = deps.stream_manager
    if stream_manager is None:
        return False

    stream_manager._mic_muted = True
    try:
        _play_beep(880)  # higher tone = "recording started"

        subprocess.run([
            "sox", "-t", "alsa", "reachymini_audio_src", "-r", "16000", "-c", "2",
            str(RECORDING_PATH),
            "trim", "0", str(MAX_RECORD_SECONDS),
            "silence", "1", "0.5", SILENCE_THRESHOLD, "1", SILENCE_DURATION_S, SILENCE_THRESHOLD
        ], check=True)

        _play_beep(440)  # lower tone = "recording done"
        return True
    except Exception:
        logger.exception("Recording failed")
        return False
    finally:
        stream_manager._mic_muted = False


class MessagingTask(Tool):
    """Handles checking or sending Signal messages, via the Messaging Agent."""

    name = "handle_messaging_task"
    description = (
        "Use this whenever the person wants to check for new messages from "
        "family, wants to record and send a voice message, wants to hear back "
        "a message they just recorded, wants to send it, or wants to re-record it. "
        "Pass a short natural-language description of what they want."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "task_description": {
                "type": "string",
                "description": "What the person wants, in plain language.",
            },
        },
        "required": ["task_description"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        global _pending_recording
        task_description = kwargs.get("task_description", "")
        logger.info("Tool call: handle_messaging_task task_description=%s", task_description)

        result = messaging_agent.handle_task(task_description)
        status = result.get("status")

        if status == "need_recording":
            group = _match_group(result.get("group_name"))
            if not group:
                groups = messaging_executor.get_active_groups_list(accessed_by="messaging_agent")
                return {
                    "status": "need_group_clarification",
                    "available_groups": [g["group_name"] for g in groups],
                }

            recorded_ok = _record_message(deps)
            if not recorded_ok:
                return {"status": "recording_failed"}

            _pending_recording = {"group_id": group["group_id"], "group_name": group["group_name"]}
            return {"status": "recorded", "group_name": group["group_name"]}

        if status == "replay_recording":
            if _pending_recording is None:
                return {"status": "no_pending_recording"}
            subprocess.run(["aplay", "-D", "reachymini_audio_sink", str(RECORDING_PATH)], check=False)
            return {"status": "replayed"}

        if status == "send_recording":
            if _pending_recording is None:
                return {"status": "no_pending_recording"}
            send_result = messaging_executor.send_message(
                _pending_recording["group_id"], str(RECORDING_PATH), accessed_by="messaging_agent"
            )
            group_name = _pending_recording["group_name"]
            _pending_recording = None
            if send_result.get("status") == "sent":
                return {"status": "sent", "group_name": group_name}
            return {"status": "send_failed"}

        if status == "rerecord":
            if _pending_recording is None:
                return {"status": "no_pending_recording"}
            group_name = _pending_recording["group_name"]
            recorded_ok = _record_message(deps)
            if not recorded_ok:
                return {"status": "recording_failed"}
            return {"status": "recorded", "group_name": group_name}

        return result