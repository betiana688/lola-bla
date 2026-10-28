"""Shared audio recording utilities - hardware access and mic gain,
used by both dialogue.py (command listening) and Story 2's recording."""

import subprocess
import sys
import select
from pathlib import Path

AUDIO_DEVICE = "plughw:0,0"
MIC_GAIN = 2.5  # multiplier applied after recording - tuned by ear, confirmed clean


def release_hw():
    subprocess.run([
        "python3", "-c",
        "from reachy_mini import ReachyMini; ReachyMini(media_backend='no_media').release_media()"
    ])


def acquire_hw():
    subprocess.run([
        "python3", "-c",
        "from reachy_mini import ReachyMini; ReachyMini(media_backend='no_media').acquire_media()"
    ])


def _apply_gain(raw_path, output_path):
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw_path), "-af", f"volume={MIC_GAIN}", str(output_path)],
        check=True, capture_output=True
    )
    raw_path.unlink()


def record_fixed(output_path, seconds=5):
    """Records for a fixed duration, applies mic gain, returns output_path."""
    raw_path = Path(str(output_path) + ".raw.wav")
    subprocess.run([
        "arecord", "-D", AUDIO_DEVICE, "-f", "S16_LE", "-r", "16000", "-c", "1",
        "-d", str(seconds), str(raw_path)
    ])
    _apply_gain(raw_path, output_path)
    return output_path


def _drain_stale_stdin():
    """Clears any leftover newline sitting in stdin from a prior paste,
    which would otherwise make the next readline() return instantly."""
    while select.select([sys.stdin], [], [], 0)[0]:
        sys.stdin.readline()


def record_until_stopped(output_path):
    """Starts recording immediately, stops when Enter is pressed.
    Applies mic gain, returns output_path."""
    _drain_stale_stdin()

    raw_path = Path(str(output_path) + ".raw.wav")
    proc = subprocess.Popen([
        "arecord", "-D", AUDIO_DEVICE, "-f", "S16_LE", "-r", "16000", "-c", "1",
        str(raw_path)
    ])
    print("Recording... press Enter to stop.")
    sys.stdin.readline()
    proc.terminate()
    proc.wait()

    if not raw_path.exists() or raw_path.stat().st_size < 1000:
        raise RuntimeError(
            f"Recording produced no usable audio (stopped too early?). "
            f"File: {raw_path}, exists: {raw_path.exists()}"
        )

    _apply_gain(raw_path, output_path)
    return output_path