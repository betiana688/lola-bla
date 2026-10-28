import sqlite3
import subprocess
import requests
import uuid
from pathlib import Path

API_BASE = "http://localhost:8080"
ACCOUNT_NUMBER = "+491234567"  # TODO: replace with your real number
DB_PATH = Path(__file__).parent / "data" / "lola.db"
AUDIO_DIR = Path(__file__).parent / "data" / "audio"
AUDIO_DIR.mkdir(exist_ok=True)

def get_active_groups(conn):
    rows = conn.execute("SELECT id, signal_group_id FROM groups WHERE is_active = 1").fetchall()
    return {signal_id: our_id for (our_id, signal_id) in rows}

def find_contact(conn, group_id, source_number, source_uuid):
    row = conn.execute(
        "SELECT id FROM contacts WHERE group_id = ? AND signal_id IN (?, ?)",
        (group_id, source_number, source_uuid)
    ).fetchone()
    return row[0] if row else None

def is_own_echo(conn, timestamp):
    """True if this timestamp matches something Reachy itself already sent (Story 2)."""
    row = conn.execute(
        "SELECT 1 FROM messages WHERE direction = 'outgoing' AND timestamp = ?",
        (str(timestamp),)
    ).fetchone()
    return row is not None

def log_event(conn, message_id, event_type, status, detail=""):
    conn.execute(
        "INSERT INTO log_entries (id, message_id, occurred_at, event_type, status, detail) "
        "VALUES (?, ?, datetime('now'), ?, ?, ?)",
        (str(uuid.uuid4()), message_id, event_type, status, detail)
    )

def download_attachment(attachment_id, filename):
    resp = requests.get(f"{API_BASE}/v1/attachments/{attachment_id}")
    resp.raise_for_status()

    raw_ext = Path(filename).suffix or ".bin"
    raw_path = AUDIO_DIR / f"{uuid.uuid4()}{raw_ext}"
    raw_path.write_bytes(resp.content)

    wav_path = raw_path.with_suffix(".wav")
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(raw_path), str(wav_path)],
        check=True, capture_output=True
    )
    raw_path.unlink()  # remove the original compressed file, keep only the WAV

    return str(wav_path)

def extract_content_message(envelope, conn):
    """
    Returns the relevant message payload, or None if this envelope should be skipped.
    - dataMessage: a message from someone else -> always relevant
    - syncMessage.sentMessage: something sent from this account (your phone, or Reachy
      itself) -> relevant only if it's NOT an echo of something Reachy already sent
    """
    if envelope.get("dataMessage"):
        return envelope["dataMessage"]

    sync_message = envelope.get("syncMessage", {}).get("sentMessage")
    if sync_message:
        if is_own_echo(conn, envelope.get("timestamp")):
            return None  # Reachy's own outgoing message, already known
        return sync_message  # a message Betiana sent from her own phone

    return None

def sync_messages():
    conn = sqlite3.connect(DB_PATH)
    active_groups = get_active_groups(conn)

    resp = requests.get(f"{API_BASE}/v1/receive/{ACCOUNT_NUMBER}")
    resp.raise_for_status()
    envelopes = resp.json()

    for entry in envelopes:
        envelope = entry.get("envelope", {})
        content_message = extract_content_message(envelope, conn)
        if not content_message:
            continue

        group_info = content_message.get("groupInfo")
        if not group_info:
            continue  # skip direct (non-group) messages entirely

        signal_group_id = group_info.get("groupId")
        our_group_id = active_groups.get(signal_group_id)
        if not our_group_id:
            continue

        source_number = envelope.get("sourceNumber")
        source_uuid = envelope.get("sourceUuid")
        contact_id = find_contact(conn, our_group_id, source_number, source_uuid)

        message_id = str(uuid.uuid4())

        if not contact_id:
            log_event(conn, message_id, "unknown_sender", "ignored",
                       f"source_number={source_number!r} source_uuid={source_uuid!r}")
            continue

        attachments = content_message.get("attachments", [])
        audio_attachments = [a for a in attachments if a.get("contentType", "").startswith("audio/")]

        if not audio_attachments:
            log_event(conn, message_id, "non_audio_message", "ignored",
                       "Message had no audio attachment")
            continue

        for attachment in audio_attachments:
            audio_path = download_attachment(attachment["id"], attachment["filename"])
            conn.execute(
                "INSERT INTO messages (id, group_id, contact_id, direction, audio_path, timestamp, played_by_reachy) "
                "VALUES (?, ?, ?, 'incoming', ?, ?, 0)",
                (str(uuid.uuid4()), our_group_id, contact_id, audio_path, str(envelope.get("timestamp")))
            )
            log_event(conn, message_id, "message_synced", "success")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    sync_messages()
    print("Sync complete.")