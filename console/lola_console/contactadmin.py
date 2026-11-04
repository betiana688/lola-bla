"""Approved contacts: list, add from the Signal contact list, rename, remove.
Never prints or logs a contact's name or phone number."""

import hashlib
import hmac
import uuid

from . import link, signal_api
from .groupadmin import GroupError as ContactError
from .groupadmin import _delete_audio, _key, _plural, clean_name

LIST_MAX = 200


def ref_for(secret, number):
    """An opaque handle for a phone number, so a form can name a contact without containing the number."""
    return hmac.new(secret, b"contact-ref:" + number.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def shown_number(signal_id):
    return link.mask_number(signal_id) if signal_id.startswith("+") else "a Signal ID"


def group_info(con, group_id):
    row = con.execute("SELECT id, name, is_active FROM groups WHERE id = ?", (group_id,)).fetchone()
    return {"id": row[0], "name": row[1], "active": bool(row[2])} if row else None


def list_contacts(con, group_id):
    rows = con.execute(
        "SELECT c.id, c.name, c.signal_id, (SELECT COUNT(*) FROM messages m WHERE m.contact_id = c.id) "
        "FROM contacts c WHERE c.group_id = ? ORDER BY c.name COLLATE NOCASE", (group_id,)).fetchall()
    return [{"id": r[0], "name": r[1], "number": shown_number(r[2]), "messages": r[3]} for r in rows]


def _check_unique(con, group_id, name, exclude_id=None):
    key = _key(name)
    if not key:
        raise ContactError("The name needs at least one letter or digit.")
    for contact_id, other in con.execute("SELECT id, name FROM contacts WHERE group_id = ?", (group_id,)):
        if contact_id != exclude_id and _key(other) == key:
            raise ContactError("Another contact in this group already has a name that sounds the same. "
                               "Pick a different name.")


def _account(con):
    return con.execute("SELECT id, signal_number FROM accounts LIMIT 1").fetchone()


def available_from_signal(con, api, secret, group_id, query=""):
    """The people in the Signal contact list who can be approved in this group:
    {"items": [...], "message": text or None}. Only people with a phone number, not blocked."""
    row = _account(con)
    if not row:
        return {"items": [], "message": "Link the Signal account first (Signal account page)."}
    try:
        found = api.contacts(row[1])
    except signal_api.SignalApiError:
        return {"items": [], "message": "Could not read your Signal contacts right now. Nothing was changed."}
    have = {r[0] for r in con.execute("SELECT signal_id FROM contacts WHERE group_id = ?", (group_id,))}
    q = (query or "").strip().casefold()
    items = []
    for c in found:
        if c["blocked"] or c["number"] in have:
            continue
        if q and q not in c["name"].casefold():
            continue
        items.append({"ref": ref_for(secret, c["number"]), "name": c["name"] or "(no name in Signal)",
                      "default_name": c["name"], "number": link.mask_number(c["number"])})
    items.sort(key=lambda i: i["name"].casefold())
    message = None
    if not items:
        message = ("No contacts match your search." if q else
                   "Everyone in your Signal contacts who has a phone number is already approved here, or blocked.")
    return {"items": items[:LIST_MAX], "message": message}


def add_contact(con, api, secret, group_id, ref, name, who):
    if not con.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone():
        raise ContactError("That group no longer exists.")
    row = _account(con)
    if not row:
        raise ContactError("Link the Signal account first.")
    try:
        found = api.contacts(row[1])
    except signal_api.SignalApiError:
        raise ContactError("Could not read your Signal contacts right now. Nothing was changed.") from None
    match = None
    if ref.isascii():
        match = next((c for c in found if not c["blocked"] and hmac.compare_digest(ref_for(secret, c["number"]), ref)), None)
    if not match:
        raise ContactError("That person was not found in your Signal contacts. Nothing was changed.")
    if con.execute("SELECT 1 FROM contacts WHERE group_id = ? AND signal_id = ?", (group_id, match["number"])).fetchone():
        raise ContactError("That person is already approved in this group.")
    spoken = clean_name(name or match["name"], what="contact")
    _check_unique(con, group_id, spoken)
    contact_id = str(uuid.uuid4())
    with con:
        con.execute("INSERT INTO contacts (id, group_id, name, signal_id) VALUES (?, ?, ?, ?)",
                    (contact_id, group_id, spoken, match["number"]))
        link.audit(con, who, "contacts", contact_id, "contact_added")
        link.activity(con, "contact_added", "ok", "A contact was approved")
    return contact_id


def rename_contact(con, contact_id, name, who):
    """Returns the id of the group the contact belongs to."""
    row = con.execute("SELECT group_id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise ContactError("That contact no longer exists.")
    spoken = clean_name(name, what="contact")
    _check_unique(con, row[0], spoken, exclude_id=contact_id)
    with con:
        con.execute("UPDATE contacts SET name = ? WHERE id = ?", (spoken, contact_id))
        link.audit(con, who, "contacts", contact_id, "contact_renamed")
    return row[0]


def remove_contact(con, contact_id, who, audio_dir):
    """Delete the contact, their messages and the audio files of those messages. Cannot be undone."""
    row = con.execute("SELECT group_id FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    if not row:
        raise ContactError("That contact no longer exists.")
    paths = [r[0] for r in con.execute("SELECT audio_path FROM messages WHERE contact_id = ?", (contact_id,))]
    with con:
        con.execute("UPDATE log_entries SET message_id = NULL "
                    "WHERE message_id IN (SELECT id FROM messages WHERE contact_id = ?)", (contact_id,))
        con.execute("DELETE FROM messages WHERE contact_id = ?", (contact_id,))
        con.execute("DELETE FROM contacts WHERE id = ?", (contact_id,))
        link.audit(con, who, "contacts", contact_id, "contact_removed")
        link.activity(con, "contact_removed", "ok", f"A contact was removed ({len(paths)} messages)")
    deleted, left = _delete_audio(paths, audio_dir)
    return {"group_id": row[0], "messages": len(paths), "files_deleted": deleted, "files_left": left}


def removal_summary(result):
    text = (f"Contact removed. Deleted {_plural(result['messages'], 'message')} "
            f"and {_plural(result['files_deleted'], 'audio file')}.")
    if result["files_left"]:
        text += (f" {result['files_left']} audio file(s) left alone "
                 "(outside the app's audio folder, or could not be deleted).")
    return text
