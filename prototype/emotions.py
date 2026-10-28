"""Reachy emotion playback - isolated here so any hardware flakiness here
can never break the actual message-reading logic in dialogue.py."""

import subprocess

DATASET = "pollen-robotics/reachy-mini-emotions-library"

EMOTION_MAP = {
    "ask_group": "curious1",
    "new_messages": "cheerful1",
    "no_messages": "no1",
    "playing_message": "attentive1",
    "retry_group": "confused1",
    "group_not_found": "lost1",
    "all_done": "success1",
    "paused": "oops1",
    "give_up": "no_sad1",
    "recording": "attentive1",
    "ask_choice": "curious1",
    "sent": "success1",
    "send_failed": "oops1",
    "deleted": "no1",
}


def play_emotion_async(state_key):
    """Fire-and-forget: starts the emotion animation in a separate process
    so it runs concurrently with whatever speak() does next. Never raises -
    a failed animation should never interrupt the actual conversation."""
    clip_name = EMOTION_MAP.get(state_key)
    if not clip_name:
        return

    code = (
        "from reachy_mini import ReachyMini; "
        "from reachy_mini.motion.recorded_move import RecordedMoves; "
        "r = ReachyMini(media_backend='no_media'); "
        "r.enable_motors(); "
        f"m = RecordedMoves('{DATASET}').get('{clip_name}'); "
        "r.play_move(m, initial_goto_duration=1.0, sound=False)"
    )
    try:
        subprocess.Popen(
            ["python3", "-c", code],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    except Exception as e:
        print(f"[emotion] failed to start '{clip_name}': {e}")


def wake_up():
    """Moves Reachy to its wake/ready position."""
    from reachy_mini import ReachyMini
    with ReachyMini(media_backend='no_media') as r:
        r.enable_motors()
        r.wake_up()


def go_to_sleep():
    """Moves Reachy to its power-off/sleep position."""
    from reachy_mini import ReachyMini
    with ReachyMini(media_backend='no_media') as r:
        r.enable_motors()
        r.goto_sleep()