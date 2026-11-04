"""Signal account status, linking and unlinking, kept apart from the web layer so it can be
tested alone. Never prints or logs a phone number."""

import uuid

from . import signal_api, users

DEVICE_NAME = "reachy-mini"
LINK_WINDOW_S = 600
UNLINK_DONE = (
    "Unlinked. The robot has stopped using the Signal account and the app's local Signal data is deleted. "
    "One step is left that only you can do: in Signal on your phone, open Settings, then Linked devices, "
    "and remove 'reachy-mini' if it is still there. This console cannot check that once the number is unregistered.")


def mask_number(number):
    if not number:
        return None
    if len(number) <= 6:
        return "\u2022" * len(number)
    return number[:3] + "\u2022" * (len(number) - 5) + number[-2:]


def audit(con, who, table, record_id, operation):
    con.execute(
        "INSERT INTO audit_log (id, accessed_by, table_name, record_id, operation, occurred_at) "
        "VALUES (?, ?, ?, ?, ?, datetime('now'))", (str(uuid.uuid4()), who, table, record_id, operation))


def activity(con, event_type, status, detail):
    con.execute(
        "INSERT INTO log_entries (id, message_id, occurred_at, event_type, status, detail) "
        "VALUES (?, NULL, datetime('now'), ?, ?, ?)", (str(uuid.uuid4()), event_type, status, detail))


def _read_state(con, api, device_name):
    row = con.execute("SELECT signal_number, device_id, device_created_at, linked_at FROM accounts LIMIT 1").fetchone()
    number = row[0] if row else None
    result = {"state": "unknown", "number_masked": mask_number(number),
              "device_id": row[1] if row else None, "linked_at": row[3] if row else None, "can_link": False,
              "message": "The Signal API did not answer properly. Nothing was changed."}
    try:
        registered = api.accounts()
    except signal_api.SignalApiError:
        if number:  # after a removal on the phone the account list can error, but our own number says so
            try:
                api.devices(number)
            except signal_api.NotRegistered:
                result.update(state="not_linked", message="Signal says this device is not registered any more.")
            except signal_api.SignalApiError:
                pass
        return result
    if not registered:
        result.update(state="not_linked", can_link=True, message="No Signal account is linked to the robot yet.")
        return result
    if not number or number not in registered:
        result.update(state="different", message="The Signal API already has an account that is not the one set up "
                                                 "here. Nothing was changed.")
        return result
    try:
        devices = api.devices(number)
    except signal_api.NotRegistered:
        result.update(state="not_linked", message="Signal says this device is not registered any more.")
        return result
    except signal_api.SignalApiError:
        return result
    ours = any(
        (row[1] is None and d["name"] == device_name) or
        (row[1] is not None and d["id"] == row[1] and (row[2] is None or str(d["creation_timestamp"]) == str(row[2])))
        for d in devices)
    if ours:
        result.update(state="linked", message="The robot is linked to your Signal account.")
    else:
        result.update(state="removed", message="The Signal account is registered, but the robot's device is no "
                                               "longer on its device list. It was probably removed in Signal on your phone.")
    return result


def _unlink_pending(con):
    """True if the last unlink attempt stopped partway."""
    row = con.execute("SELECT event_type FROM log_entries WHERE event_type IN ('unlink_failed', 'unlink_done') "
                      "ORDER BY occurred_at DESC, rowid DESC LIMIT 1").fetchone()
    return bool(row) and row[0] == "unlink_failed"


def read_status(con, api, device_name=DEVICE_NAME):
    """What Signal says about the robot's link, plus which unlink button (if any) makes sense.
    Reads only: it never changes anything."""
    result = _read_state(con, api, device_name)
    row = con.execute("SELECT status FROM accounts LIMIT 1").fetchone()
    db_status = row[0] if row else None
    result["unlink"] = None
    if row and result["state"] in ("linked", "not_linked", "removed"):
        if _unlink_pending(con):
            result["unlink"] = "finish"
        elif db_status == "linked":
            result["unlink"] = "unlink" if result["state"] == "linked" else "cleanup"
        elif result["state"] in ("linked", "removed"):
            result["unlink"] = "finish"
    if row and result["state"] == "linked" and db_status != "linked":
        result.update(state="unfinished", can_link=False,
                      message="The robot is marked unlinked here, but the Signal API still has the account. "
                              "Finish unlinking to clean it up.")
    return result


def _refuse(con, who, text):
    with con:
        audit(con, who, "accounts", None, "link_refused")
        activity(con, "link_refused", "failed", text)
    return "refused", text


def finish_link(con, api, user_id, who, device_name=DEVICE_NAME):
    """Called while a link is in progress. Returns (outcome, text): 'waiting', 'linked' or 'refused'.
    Nothing is recorded unless the scan is clearly the right one."""
    try:
        registered = api.accounts()
    except signal_api.SignalApiError:
        return "waiting", None  # the API may still be busy right after the scan
    if not registered:
        return "waiting", None
    if len(registered) != 1:
        return _refuse(con, who, "More than one Signal account is registered in the Signal API. Nothing was recorded.")
    number = registered[0]
    try:
        devices = api.devices(number)
    except signal_api.SignalApiError:
        return "waiting", None
    mine = [d for d in devices if d["name"] == device_name]
    if not mine:
        return "waiting", None
    if len(mine) > 1:
        return _refuse(con, who, f"More than one device is called '{device_name}' on this Signal account. Nothing was recorded.")
    device = mine[0]
    row = con.execute("SELECT id, signal_number FROM accounts LIMIT 1").fetchone()
    if row and row[1] != number:
        return _refuse(con, who, "You scanned a different Signal account than the one your groups belong to, so nothing "
                                 "was recorded. Remove the new device in Signal on your phone.")
    created = str(device["creation_timestamp"])
    with con:
        if row:
            account_id = row[0]
            con.execute(f"UPDATE accounts SET status = 'linked', device_id = ?, device_created_at = ?, "
                        f"linked_at = {users.NOW}, user_id = COALESCE(user_id, ?) WHERE id = ?",
                        (device["id"], created, user_id, account_id))
        else:
            account_id = str(uuid.uuid4())
            con.execute(f"INSERT INTO accounts (id, user_id, signal_number, status, device_id, device_created_at, linked_at) "
                        f"VALUES (?, ?, ?, 'linked', ?, ?, {users.NOW})",
                        (account_id, user_id, number, device["id"], created))
        audit(con, who, "accounts", account_id, "account_linked")
        activity(con, "account_linked", "ok", "The robot's Signal device was linked")
    return "linked", None


def _unlink_failed(con, who, account_id, label, why):
    with con:
        audit(con, who, "accounts", account_id, "unlink_failed")
        activity(con, "unlink_failed", "failed", f"Unlinking stopped at: {label} ({why})")
    return "partial", (f"Unlinking did not finish: it stopped at '{label}'. Reachy is already marked unlinked. "
                       "Press the button again to finish the rest.")


def unlink(con, api, who):
    """The guided unlink. Returns (outcome, text): 'done', 'partial' or 'refused'.
    The robot is marked unlinked first, so Reachy stops using the account at once. The Signal
    account itself is never deleted: the client has no way to ask for that."""
    row = con.execute("SELECT id, signal_number FROM accounts LIMIT 1").fetchone()
    if not row:
        return "refused", "There is no Signal account recorded, so there is nothing to unlink."
    account_id, number = row
    try:
        registered = api.accounts()
    except signal_api.SignalApiError:
        registered = None  # after a removal on the phone this list can fail; the steps below cope with it
    if registered and registered != [number]:
        return "refused", "The Signal API has a different account than the one recorded here, so nothing was changed."
    with con:
        con.execute("UPDATE accounts SET status = 'unlinked' WHERE id = ?", (account_id,))
        audit(con, who, "accounts", account_id, "unlink_started")
    steps = (("stop using the account (unregister)", api.unregister),
             ("delete the app's local Signal data", api.delete_local_data))
    for label, step in steps:
        try:
            step(number)
        except signal_api.NotRegistered:
            continue  # already not registered: nothing to do for this step
        except signal_api.SignalApiError as e:
            return _unlink_failed(con, who, account_id, label, str(e))
    try:
        still = api.accounts()
    except signal_api.SignalApiError:
        still = None
    if still and number in still:
        return _unlink_failed(con, who, account_id, "check that the account is gone", "the Signal API still lists it")
    with con:
        audit(con, who, "accounts", account_id, "account_unlinked")
        activity(con, "unlink_done", "ok", "Unlinked from the console")
    return "done", UNLINK_DONE
