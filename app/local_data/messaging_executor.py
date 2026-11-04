"""Local Tool Executor - the actual check_messages/send_message logic.
Runs entirely on the Pi; the Conversational Agent never sees this code
or its data directly, only whatever the calling tool chooses to return.

The linked Signal account lives in the database (accounts table), not in code."""

import base64
import subprocess
import sqlite3
import threading
import time
import uuid
import requests
from pathlib import Path
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

API_BASE = "http://localhost:8080"

# Deliberately generous. The Signal API handles one account operation at a time and a
# receive can take minutes after a long silence. Giving up early could abandon messages
# Signal has already handed over, so waiting is the cautious choice until receiving
# moves to a background job.
RECEIVE_TIMEOUT_S = 150
SEND_TIMEOUT_S = 60
DOWNLOAD_TIMEOUT_S = 60

# A check reads the database directly if a sync finished less than this long ago.
FRESH_S = 300
_sync_lock = threading.Lock()  # syncs never overlap
_last_sync_ok = -1e9           # time.monotonic() of the last good sync

BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "lola.db"
AUDIO_DIR = BASE_DIR / "audio"
AUDIO_DIR.mkdir(exist_ok=True)

TIMEZONE = ZoneInfo("Europe/Berlin")


class NotLinkedError(Exception):
    """Signal says this device is no longer registered to the account."""


def _get_conn():
    return sqlite3.connect(DB_PATH, timeout=30)


def _log_audit(conn, accessed_by, table_name, record_id, operation):
    conn.execute(
        "INSERT INTO audit_log (id, accessed_by, table_name, record_id, operation, occurred_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))",
        (str(uuid.uuid4()), accessed_by, table_name, record_id, operation)
    )


def _log_event(conn, event_type, status, detail=None, message_id=None):
    """Activity log entry. Never put phone numbers in `detail`."""
    conn.execute(
        "INSERT INTO log_entries (id, message_id, occurred_at, event_type, status, detail) "
        "VALUES (?, ?, datetime('now'), ?, ?, ?)",
        (str(uuid.uuid4()), message_id, event_type, status, detail)
    )


def get_linked_number(conn):
    row = conn.execute("SELECT signal_number FROM accounts WHERE status = 'linked' LIMIT 1").fetchone()
    return row[0] if row else None


def is_linked():
    """True if the Signal account is currently marked as linked. Reads the database only."""
    conn = _get_conn()
    try:
        return get_linked_number(conn) is not None
    finally:
        conn.close()


def _mark_unlinked(conn, accessed_by):
    conn.execute("UPDATE accounts SET status = 'unlinked' WHERE status = 'linked'")
    _log_audit(conn, accessed_by, "accounts", None, "write")
    _log_event(conn, "account_unlinked", "detected",
               "Signal reports this device is no longer registered to the account")
    conn.commit()


def log_event(event_type, status, detail=None):
    """Public activity-log entry for failures outside this module (for example in
    the tool). Never put phone numbers in `detail`."""
    conn = _get_conn()
    try:
        _log_event(conn, event_type, status, detail)
        conn.commit()
    finally:
        conn.close()


def _is_not_registered(resp):
    return resp.status_code == 400 and "is not registered" in resp.text


def _get_active_groups(conn):
    rows = conn.execute("SELECT id, signal_group_id FROM groups WHERE is_active = 1").fetchall()
    return {signal_id: our_id for (our_id, signal_id) in rows}


def _group_name(conn, group_id):
    row = conn.execute("SELECT name FROM groups WHERE id = ?", (group_id,)).fetchone()
    return row[0] if row else "unknown"


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
    resp = requests.get(f"{API_BASE}/v1/attachments/{attachment_id}", timeout=DOWNLOAD_TIMEOUT_S)
    resp.raise_for_status()

    raw_ext = Path(filename).suffix or ".bin"
    raw_path = AUDIO_DIR / f"{uuid.uuid4()}{raw_ext}"
    raw_path.write_bytes(resp.content)

    wav_path = raw_path.with_suffix(".wav")
    subprocess.run(["ffmpeg", "-y", "-i", str(raw_path), "-ar", "16000", "-ac", "2", str(wav_path)],
                   check=True, capture_output=True, timeout=60)
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


def _sync_messages(conn, accessed_by, number):
    active_groups = _get_active_groups(conn)
    resp = requests.get(f"{API_BASE}/v1/receive/{number}", timeout=RECEIVE_TIMEOUT_S)
    if _is_not_registered(resp):
        raise NotLinkedError()
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

        our_group_id = active_groups.get(group_info.get("groupId"))
        if not our_group_id:
            continue

        contact_id = _find_contact(conn, our_group_id, envelope.get("sourceNumber"), envelope.get("sourceUuid"))
        if not contact_id:
            _log_event(conn, "unknown_sender", "ignored",
                       f"Ignored a message in approved group '{_group_name(conn, our_group_id)}' "
                       "from someone who is not an approved contact")
            conn.commit()
            continue

        audio_attachments = [a for a in content_message.get("attachments", [])
                             if a.get("contentType", "").startswith("audio/")]
        for attachment in audio_attachments:
            try:
                audio_path = _download_attachment(attachment["id"], attachment["filename"])
            except Exception as e:
                _log_event(conn, "download_failed", "failed",
                           f"Could not download an incoming voice message ({type(e).__name__})")
                conn.commit()
                continue
            msg_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO messages (id, group_id, contact_id, direction, audio_path, timestamp, played_by_reachy) "
                "VALUES (?, ?, ?, 'incoming', ?, ?, 0)",
                (msg_id, our_group_id, contact_id, audio_path, str(envelope.get("timestamp")))
            )
            _log_audit(conn, accessed_by, "messages", msg_id, "write")
            conn.commit()


def _sync_if_stale(conn, accessed_by, number, max_age_s=None):
    """Pull new messages from Signal unless a sync finished less than max_age_s ago
    (default FRESH_S). Syncs never overlap: a caller that arrives mid-sync waits for
    it and then usually finds the data fresh."""
    global _last_sync_ok
    limit = FRESH_S if max_age_s is None else max_age_s
    with _sync_lock:
        if time.monotonic() - _last_sync_ok < limit:
            return
        _sync_messages(conn, accessed_by, number)
        _last_sync_ok = time.monotonic()


def sync_now(accessed_by="background_sync"):
    """One background sync. Returns (status, error_name) where status is 'ok',
    'not_linked' or 'failed'. Never raises."""
    try:
        conn = _get_conn()
    except Exception as e:
        return "failed", type(e).__name__
    try:
        number = get_linked_number(conn)
        if not number:
            return "not_linked", None
        try:
            _sync_if_stale(conn, accessed_by, number, max_age_s=60)
            return "ok", None
        except NotLinkedError:
            _mark_unlinked(conn, accessed_by)
            return "not_linked", None
        except Exception as e:
            conn.rollback()
            return "failed", type(e).__name__
    except Exception as e:
        return "failed", type(e).__name__
    finally:
        conn.close()


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
    summary dict for the Messaging Agent to relay - never raw audio.
    Returns {"status": "not_linked"} if the Signal account is not linked."""
    conn = _get_conn()
    try:
        number = get_linked_number(conn)
        if not number:
            return {"status": "not_linked"}

        try:
            _sync_if_stale(conn, accessed_by, number)
        except NotLinkedError:
            _mark_unlinked(conn, accessed_by)
            return {"status": "not_linked"}
        except Exception as e:
            conn.rollback()
            _log_event(conn, "sync_failed", "failed",
                       f"Could not check Signal for new messages ({type(e).__name__}); "
                       "showing what was already received")
            conn.commit()

        candidates = conn.execute(
            "SELECT DISTINCT g.id, g.name FROM groups g "
            "JOIN messages m ON m.group_id = g.id "
            "WHERE g.is_active = 1 AND m.played_by_reachy = 0 AND m.direction = 'incoming'"
        ).fetchall()
        _log_audit(conn, accessed_by, "groups", None, "read")

        if not candidates:
            conn.commit()
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
    ever gets a status back: sent, failed, or not_linked."""
    conn = _get_conn()
    try:
        number = get_linked_number(conn)
        if not number:
            return {"status": "not_linked"}

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
            "number": number,
            "recipients": [recipient],
            "base64_attachments": [audio_b64],
        }

        try:
            resp = requests.post(f"{API_BASE}/v2/send", json=payload, timeout=SEND_TIMEOUT_S)
        except requests.exceptions.RequestException as e:
            _log_event(conn, "send_failed", "failed", f"Could not reach Signal to send ({type(e).__name__})")
            conn.commit()
            return {"status": "failed"}

        if _is_not_registered(resp):
            _mark_unlinked(conn, accessed_by)
            return {"status": "not_linked"}
        if not resp.ok:
            _log_event(conn, "send_failed", "failed", f"Signal refused the message (HTTP {resp.status_code})")
            conn.commit()
            return {"status": "failed"}

        sent_timestamp = resp.json().get("timestamp")
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
