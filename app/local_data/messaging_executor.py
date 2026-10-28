"""Local Tool Executor - the actual check_messages/send_message logic.
Runs entirely on the Pi; the Conversational Agent never sees this code
or its data directly, only whatever the calling tool chooses to return."""

import base64
import os
import subprocess
import sqlite3
import uuid
import requests
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

API_BASE = "http://localhost:8080"
ACCOUNT_NUMBER = os.environ.get("LOLA_SIGNAL_NUMBER", "YOUR_ACTUAL_NUMBER_HERE")  # linked Signal number, e.g. +49...

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "lola.db"
AUDIO_DIR = BASE_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)

TIMEZONE = ZoneInfo("Europe/Berlin")


def _get_conn():
    return sqlite3.connect(DB_PATH)


def _log_audit(conn, accessed_by, table_name, record_id, operation):
    conn.execute(
        "INSERT INTO audit_log (id, accessed_by, table_name, record_id, operation, occurred_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (str(uuid.uuid4()), accessed_by, table_name, record_id, operation)
    )


def _get_active_groups(conn):
    rows = conn.execute("SELECT id, signal_group_id FROM groups WHERE is_active = 1").fetchall()
    return {signal_id: our_id for (our_id, signal_id) in rows}


def _find_contact(conn, group_id, source_number, source_uuid):
    row = conn.execute(
        "SELECT id FROM contacts WHERE group_id = ? AND signal_id IN (?, ?)",
        (group_id, source_number, source_uuid)
    ).fetchone()
    return row[0] if row else None


def _is_own_echo(conn, timestamp):
    row = conn.execute(
        "SELECT 1 FROM messages WHERE direction = 'outgoing' AND timestamp = ?",
        (str(timestamp),)
    ).fetchone()
    return row is not None


def _download_attachment(attachment_id, filename):
    resp = requests.get(f"{API_BASE}/v1/attachments/{attachment_id}")
    resp.raise_for_status()

    raw_ext = Path(filename).suffix or ".bin"
    raw_path = AUDIO_DIR / f"{uuid.uuid4()}{raw_ext}"
    raw_path.write_bytes(resp.content)

    wav_path = raw_path.with_suffix(".wav")
    subprocess.run(["ffmpeg", "-y", "-i", str(raw_path), "-ar", "16000", "-ac", "2", str(wav_path)], check=True, capture_output=True)
    raw_path.unlink()
    return str(wav_path)


def _extract_content_message(envelope, conn):
    if envelope.get("dataMessage"):
        return envelope["dataMessage"]
    sync_message = envelope.get("syncMessage", {}).get("sentMessage")
    if sync_message:
        if _is_own_echo(conn, envelope.get("timestamp")):
            return None
        return sync_message
    return None


def _sync_messages(conn, accessed_by):
    active_groups = _get_active_groups(conn)
    resp = requests.get(f"{API_BASE}/v1/receive/{ACCOUNT_NUMBER}")
    resp.raise_for_status()
    envelopes = resp.json()

    for entry in envelopes:
        envelope = entry.get("envelope", {})
        content_message = _extract_content_message(envelope, conn)
        if not content_message:
            continue

        group_info = content_message.get("groupInfo")
        if not group_info:
            continue

        signal_group_id = group_info.get("groupId")
        our_group_id = active_groups.get(signal_group_id)
        if not our_group_id:
            continue

        source_number = envelope.get("sourceNumber")
        source_uuid = envelope.get("sourceUuid")
        contact_id = _find_contact(conn, our_group_id, source_number, source_uuid)
        if not contact_id:
            continue

        attachments = content_message.get("attachments", [])
        audio_attachments = [a for a in attachments if a.get("contentType", "").startswith("audio/")]
        for attachment in audio_attachments:
            audio_path = _download_attachment(attachment["id"], attachment["filename"])
            msg_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO messages (id, group_id, contact_id, direction, audio_path, timestamp, played_by_reachy) "
                "VALUES (?, ?, ?, 'incoming', ?, ?, 0)",
                (msg_id, our_group_id, contact_id, audio_path, str(envelope.get("timestamp")))
            )
            _log_audit(conn, accessed_by, "messages", msg_id, "write")

    conn.commit()


def _format_day_and_time(timestamp_ms):
    dt = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=TIMEZONE)
    now = datetime.now(tz=TIMEZONE)
    time_str = dt.strftime("%H:%M")
    if dt.date() == now.date():
        return "today", time_str
    elif dt.date() == (now - timedelta(days=1)).date():
        return "yesterday", time_str
    else:
        return dt.strftime("%A %d %B"), time_str


def check_messages(accessed_by="messaging_agent"):
    """Checks all active groups for unplayed messages. Returns a plain-language
    summary dict for the Messaging Agent to relay - never raw audio."""
    conn = _get_conn()
    try:
        _sync_messages(conn, accessed_by)

        candidates = conn.execute(
            "SELECT DISTINCT g.id, g.name FROM groups g "
            "JOIN messages m ON m.group_id = g.id "
            "WHERE g.is_active = 1 AND m.played_by_reachy = 0 AND m.direction = 'incoming'"
        ).fetchall()
        _log_audit(conn, accessed_by, "groups", None, "read")

        if not candidates:
            return {"status": "no_new_messages"}

        results = []
        for group_id, group_name in candidates:
            messages = conn.execute(
                "SELECT m.id, c.name, m.timestamp, m.audio_path FROM messages m "
                "JOIN contacts c ON m.contact_id = c.id "
                "WHERE m.group_id = ? AND m.played_by_reachy = 0 AND m.direction = 'incoming' "
                "ORDER BY m.timestamp ASC",
                (group_id,)
            ).fetchall()
            _log_audit(conn, accessed_by, "messages", group_id, "read")

            message_list = []
            for msg_id, sender_name, timestamp, audio_path in messages:
                day_str, time_str = _format_day_and_time(timestamp)
                message_list.append({
                    "message_id": msg_id,
                    "sender": sender_name,
                    "day": day_str,
                    "time": time_str,
                    "audio_path": audio_path,
                })
            results.append({"group_id": group_id, "group_name": group_name, "messages": message_list})

        conn.commit()
        return {"status": "found_messages", "groups": results}
    finally:
        conn.close()


def mark_played(message_id, accessed_by="messaging_agent"):
    """Marks a message as played, and returns its audio_path so the caller
    (the tool) can actually play it through Reachy's speaker."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT audio_path FROM messages WHERE id = ?", (message_id,)).fetchone()
        if not row:
            return {"error": "message not found"}
        conn.execute("UPDATE messages SET played_by_reachy = 1 WHERE id = ?", (message_id,))
        _log_audit(conn, accessed_by, "messages", message_id, "write")
        conn.commit()
        return {"status": "marked_played", "audio_path": row[0]}
    finally:
        conn.close()


def get_active_groups_list(accessed_by="messaging_agent"):
    """Returns the list of active groups, for resolving which one to send to."""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT id, name FROM groups WHERE is_active = 1").fetchall()
        _log_audit(conn, accessed_by, "groups", None, "read")
        conn.commit()
        return [{"group_id": gid, "group_name": name} for gid, name in rows]
    finally:
        conn.close()


def send_message(group_id, recording_path, accessed_by="messaging_agent"):
    """Sends a locally-recorded message to a group. The recording never
    leaves this function except to Signal's own API - the caller only
    ever gets success/failure back."""
    conn = _get_conn()
    try:
        row = conn.execute("SELECT signal_group_id FROM groups WHERE id = ?", (group_id,)).fetchone()
        if not row:
            return {"error": "group not found"}
        internal_id = row[0]
        _log_audit(conn, accessed_by, "groups", group_id, "read")

        with open(recording_path, "rb") as f:
            audio_b64 = base64.b64encode(f.read()).decode()
        recipient = f"group.{base64.b64encode(internal_id.encode()).decode()}"

        payload = {
            "message": "",
            "number": ACCOUNT_NUMBER,
            "recipients": [recipient],
            "base64_attachments": [audio_b64],
        }

        try:
            resp = requests.post(f"{API_BASE}/v2/send", json=payload, timeout=30)
            if not resp.ok:
                return {"status": "failed", "detail": f"{resp.status_code}: {resp.text}"}
            sent_timestamp = resp.json().get("timestamp")
        except requests.exceptions.RequestException as e:
            return {"status": "failed", "detail": str(e)}

        msg_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO messages (id, group_id, contact_id, direction, audio_path, timestamp, played_by_reachy) "
            "VALUES (?, ?, NULL, 'outgoing', ?, ?, 1)",
            (msg_id, group_id, str(recording_path), str(sent_timestamp))
        )
        _log_audit(conn, accessed_by, "messages", msg_id, "write")
        conn.commit()
        return {"status": "sent"}
    finally:
        conn.close()