"""Approved groups: list, add from Signal, rename, activate or deactivate, remove.
Never prints or logs a group name, a phone number or a member ID."""

import re
import uuid
from pathlib import Path

from . import link, signal_api

NAME_MAX = 40
LIST_MAX = 200


class GroupError(Exception):
    """Something the person can fix. The text is safe to show."""


def clean_name(text):
    name = re.sub(r"\s+", " ", text or "").strip()
    if not name:
        raise GroupError("Type a name for the group.")
    if len(name) > NAME_MAX:
        raise GroupError(f"The name is too long (at most {NAME_MAX} characters).")
    if any(ord(c) < 32 or ord(c) == 127 for c in name):
        raise GroupError("The name contains characters that are not allowed.")
    return name


def _key(name):
    """Names with the same key would confuse the robot, which picks a group by its name."""
    return re.sub(r"\W+", "", name.casefold().replace("&", "and"))


def _check_unique(con, name, exclude_id=None):
    key = _key(name)
    if not key:
        raise GroupError("The name needs at least one letter or digit.")
    for group_id, other in con.execute("SELECT id, name FROM groups"):
        if group_id != exclude_id and _key(other) == key:
            raise GroupError("Another approved group already has a name that sounds the same. Pick a different name.")


def _account(con):
    return con.execute("SELECT id, signal_number FROM accounts LIMIT 1").fetchone()


def list_groups(con):
    rows = con.execute(
        "SELECT g.id, g.name, g.is_active, "
        "(SELECT COUNT(*) FROM contacts c WHERE c.group_id = g.id), "
        "(SELECT COUNT(*) FROM messages m WHERE m.group_id = g.id) "
        "FROM groups g ORDER BY g.name COLLATE NOCASE").fetchall()
    return [{"id": r[0], "name": r[1], "active": bool(r[2]), "contacts": r[3], "messages": r[4]} for r in rows]


def available_from_signal(con, api, query=""):
    """The Signal groups that are not approved yet: {"items": [...], "message": text or None}."""
    row = _account(con)
    if not row:
        return {"items": [], "message": "Link the Signal account first (Signal account page)."}
    try:
        found = api.groups(row[1])
    except signal_api.SignalApiError:
        return {"items": [], "message": "Could not read the group list from Signal right now. Nothing was changed."}
    approved = {r[0] for r in con.execute("SELECT signal_group_id FROM groups")}
    q = (query or "").strip().casefold()
    items = [g for g in found if not g["blocked"] and g["internal_id"] not in approved
             and (not q or q in g["name"].casefold())]
    items.sort(key=lambda g: g["name"].casefold())
    message = None
    if not items:
        if q:
            message = "No groups match your search."
        elif found:
            message = "Every group your Signal account is in is already approved (or blocked)."
        else:
            message = "Your Signal account is not in any group."
    return {"items": items[:LIST_MAX], "message": message}


def add_group(con, api, internal_id, name, who):
    row = _account(con)
    if not row:
        raise GroupError("Link the Signal account first.")
    try:
        found = api.groups(row[1])
    except signal_api.SignalApiError:
        raise GroupError("Could not read the group list from Signal right now. Nothing was changed.") from None
    match = next((g for g in found if g["internal_id"] == internal_id and not g["blocked"]), None)
    if not match:
        raise GroupError("That group was not found in your Signal account. Nothing was changed.")
    if con.execute("SELECT 1 FROM groups WHERE signal_group_id = ?", (internal_id,)).fetchone():
        raise GroupError("That group is already approved.")
    spoken = clean_name(name or match["name"])
    _check_unique(con, spoken)
    group_id = str(uuid.uuid4())
    with con:
        con.execute("INSERT INTO groups (id, name, signal_group_id, is_active, account_id) VALUES (?, ?, ?, 1, ?)",
                    (group_id, spoken, internal_id, row[0]))
        link.audit(con, who, "groups", group_id, "group_added")
        link.activity(con, "group_added", "ok", "A group was approved")
    return group_id


def rename_group(con, group_id, name, who):
    if not con.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone():
        raise GroupError("That group no longer exists.")
    spoken = clean_name(name)
    _check_unique(con, spoken, exclude_id=group_id)
    with con:
        con.execute("UPDATE groups SET name = ? WHERE id = ?", (spoken, group_id))
        link.audit(con, who, "groups", group_id, "group_renamed")


def set_active(con, group_id, active, who):
    row = con.execute("SELECT is_active FROM groups WHERE id = ?", (group_id,)).fetchone()
    if not row:
        raise GroupError("That group no longer exists.")
    if bool(row[0]) == bool(active):
        return
    with con:
        con.execute("UPDATE groups SET is_active = ? WHERE id = ?", (1 if active else 0, group_id))
        link.audit(con, who, "groups", group_id, "group_activated" if active else "group_deactivated")


def _delete_audio(paths, audio_dir):
    """Delete the audio files that sit inside the app's audio folder. Returns (deleted, left alone).
    Anything outside that folder, and any symbolic link, is never touched."""
    base = Path(audio_dir).resolve()
    deleted = left = 0
    for text in paths:
        p = Path(text)
        if not p.is_absolute():
            p = Path(audio_dir) / p
        if p.is_symlink():
            left += 1
            continue
        if not p.exists():
            continue
        resolved = p.resolve()
        if base not in resolved.parents:
            left += 1
            continue
        try:
            resolved.unlink()
            deleted += 1
        except OSError:
            left += 1
    return deleted, left


def remove_group(con, group_id, who, audio_dir):
    """Delete the group, its contacts, its messages and their audio files. Cannot be undone."""
    if not con.execute("SELECT 1 FROM groups WHERE id = ?", (group_id,)).fetchone():
        raise GroupError("That group no longer exists.")
    paths = [r[0] for r in con.execute("SELECT audio_path FROM messages WHERE group_id = ?", (group_id,))]
    n_contacts = con.execute("SELECT COUNT(*) FROM contacts WHERE group_id = ?", (group_id,)).fetchone()[0]
    with con:
        con.execute("UPDATE log_entries SET message_id = NULL "
                    "WHERE message_id IN (SELECT id FROM messages WHERE group_id = ?)", (group_id,))
        con.execute("DELETE FROM messages WHERE group_id = ?", (group_id,))
        con.execute("DELETE FROM contacts WHERE group_id = ?", (group_id,))
        con.execute("DELETE FROM groups WHERE id = ?", (group_id,))
        link.audit(con, who, "groups", group_id, "group_removed")
        link.activity(con, "group_removed", "ok", f"A group was removed ({n_contacts} contacts, {len(paths)} messages)")
    deleted, left = _delete_audio(paths, audio_dir)
    return {"contacts": n_contacts, "messages": len(paths), "files_deleted": deleted, "files_left": left}


def _plural(n, word):
    return f"{n} {word}" + ("" if n == 1 else "s")


def removal_summary(result):
    text = (f"Group removed. Deleted {_plural(result['contacts'], 'contact')}, {_plural(result['messages'], 'message')} "
            f"and {_plural(result['files_deleted'], 'audio file')}.")
    if result["files_left"]:
        text += (f" {result['files_left']} audio file(s) left alone "
                 "(outside the app's audio folder, or could not be deleted).")
    return text
