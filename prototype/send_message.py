"""Sending an outgoing voice message via signal-cli-rest-api - Story 2, Step 4."""

import base64
import requests

API_BASE = "http://localhost:8080"
ACCOUNT_NUMBER = "YOUR_REAL_NUMBER"  # set to your actual Signal number


def to_send_recipient_id(internal_id):
    """Converts our stored raw internal_id into the 'group.<base64>' form
    that /v2/send expects in its recipients list."""
    encoded = base64.b64encode(internal_id.encode()).decode()
    return f"group.{encoded}"


def send_voice_message(audio_path, group_internal_id):
    """Sends a voice message to a group. Returns (success: bool, detail)."""
    with open(audio_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode()

    recipient = to_send_recipient_id(group_internal_id)

    payload = {
        "message": "",
        "number": ACCOUNT_NUMBER,
        "recipients": [recipient],
        "base64_attachments": [audio_b64],
    }

    try:
        resp = requests.post(f"{API_BASE}/v2/send", json=payload, timeout=30)
        if not resp.ok:
            return False, f"{resp.status_code}: {resp.text}"
        return True, resp.json()
    except requests.exceptions.RequestException as e:
        return False, str(e)