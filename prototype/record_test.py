from pathlib import Path

from audio_utils import release_hw, acquire_hw, record_until_stopped, AUDIO_DEVICE
import subprocess


if __name__ == "__main__":
    release_hw()
    out = Path(__file__).parent / "data" / "_test_recording.wav"
    input("Press Enter to start recording...")
    record_until_stopped(out)
    acquire_hw()
    print(f"Saved to {out}")
    subprocess.run(["aplay", "-D", AUDIO_DEVICE, str(out)])