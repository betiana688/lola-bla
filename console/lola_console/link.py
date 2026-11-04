"""Signal account status and linking, kept apart from the web layer so it can be tested alone.
Never prints or logs a phone number."""

import uuid

from . import signal_api, users

DEVICE_NAME = "reachy-mini"
LINK_WINDOW_S = 600


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


def read_status(con, api, device_name=DEVICE_NAME):
    """What Signal says about the robot's link. Reads only: it never changes anything."""
    row = con.execute("SELECT signal_number, device_id, device_created_at, linked_at FROM accounts LIMIT 1").fetchone()
    number = row[0] if row else None
    result = {"state": "unknown", "number_masked": mask_number(number),
              "device_id": row[1] if row else None, "linked_at": row[3] if row else None, "can_link": False,
              "message": "The Signal API did not answer properly. Nothing was changed."}
    try:
        registered = api.accounts()
    except signal_api.SignalApiError:
        if number:  # after a removal on the phone the account list errors, but our own number says so
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
