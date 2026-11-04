"""Isolated test: mute the live mic forwarding (not the device itself, which
is shared via ALSA dsnoop), record locally, unmute. Proving the mechanism
before building real logic on top of it."""

import logging
import subprocess
from pathlib import Path
from typing import Any, Dict

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies

logger = logging.getLogger(__name__)

TEST_RECORDING_PATH = Path("/tmp/mic_handoff_test.wav")


class TestMicHandoff(Tool):
    """Isolated test of muting the conversation's mic forwarding, recording
    locally for 3 seconds via the shared ALSA device, then unmuting."""

    name = "test_mic_handoff"
    description = "TEST ONLY: briefly mutes the conversation mic and records 3 seconds locally, then plays it back."
    parameters_schema = {"type": "object", "properties": {}, "required": []}

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        stream_manager = deps.stream_manager
        if stream_manager is None:
            return {"error": "stream_manager not available on deps"}

        logger.info("test_mic_handoff: muting conversation mic")
        stream_manager._mic_muted = True

        try:
            logger.info("test_mic_handoff: recording locally for 3s")
            subprocess.run([
                "arecord", "-D", "reachymini_audio_src", "-f", "S16_LE", "-r", "16000", "-c", "2",
                "-d", "3", str(TEST_RECORDING_PATH)
            ], check=True)

            logger.info("test_mic_handoff: playing back")
            subprocess.run(["aplay", "-D", "reachymini_audio_sink", str(TEST_RECORDING_PATH)], check=True)
        except Exception as e:
            logger.exception("local recording/playback failed")
            stream_manager._mic_muted = False
            return {"error": f"recording/playback failed: {e!s}"}

        logger.info("test_mic_handoff: unmuting conversation mic")
        stream_manager._mic_muted = False

        return {"status": "success", "message": "Recorded 3 seconds locally while muted, played it back, mic unmuted."}
