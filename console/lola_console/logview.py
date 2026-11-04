"""The Logs page: read-only views of the activity log and the audit log.
Numbers and IDs inside log text are masked, record IDs are shortened, and nothing here can change a log."""

import os
import re
from datetime import datetime, timezone
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

PAGE_SIZE = 50
MAX_PAGE = 10000
MAX_DETAIL = 300
VIEWS = (("activity", "Activity"), ("audit", "Audit"))
PERIODS = (("1d", "Last 24 hours", "-1 day"), ("7d", "Last 7 days", "-7 days"),
           ("30d", "Last 30 days", "-30 days"), ("all", "Everything", None))
DEFAULT_PERIOD = "7d"
FILTERS = {
    "activity": (("status", "Status", "log_entries", "status"), ("event", "Event", "log_entries", "event_type")),
    "audit": (("who", "Who", "audit_log", "accessed_by"), ("table", "Table", "audit_log", "table_name"),
              ("op", "Operation", "audit_log", "operation")),
}

_UUID = re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b")
_PHONE = re.compile(r"\+\d[\d ()-]{5,}\d")
_LONGID = re.compile(r"[A-Za-z0-9+_=-]{32,}")
_LONGDIGITS = re.compile(r"\b\d{7,}\b")


def mask_text(text):
    """A safety net, not a guarantee: phone numbers, Signal IDs and long numbers become [number] or [id]."""
    text = _UUID.sub("[id]", str(text))
    text = _PHONE.sub("[number]", text)
    text = _LONGID.sub("[id]", text)
    return _LONGDIGITS.sub("[number]", text)


def short(value):
    return "" if value is None else mask_text(str(value)[:8])


def get_zone():
    try:
        return ZoneInfo(os.environ.get("LOLA_TIMEZONE", "Europe/Berlin"))
    except Exception:
        return timezone.utc


def format_time(utc_text, zone):
    """`utc_text` is what SQLite's datetime() gives: YYYY-MM-DD HH:MM:SS in UTC. None if it is not that."""
    try:
        moment = datetime.strptime(utc_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None
    local = moment.astimezone(zone)
    return local.strftime("%d %b %Y %H:%M ") + (local.tzname() or "UTC")


def _distinct(con, table, column):
    # table and column come from the constants above, never from the request
    return [r[0] for r in con.execute(
        f"SELECT DISTINCT {column} FROM {table} WHERE {column} IS NOT NULL ORDER BY {column} LIMIT 200")]


def build_page(con, query):
    zone = get_zone()
    view = query.get("view") if query.get("view") in dict(VIEWS) else "activity"
    period = query.get("period") if query.get("period") in {p[0] for p in PERIODS} else DEFAULT_PERIOD
    try:
        page = min(max(int(str(query.get("page", "1"))), 1), MAX_PAGE)
    except ValueError:
        page = 1

    filters, where, args = [], [], []
    for name, label, table, column in FILTERS[view]:
        choices = _distinct(con, table, column)
        value = query.get(name) if query.get(name) in choices else "all"
        filters.append({"name": name, "label": label, "value": value,
                        "choices": [(c, mask_text(c)) for c in choices]})
        if value != "all":
            where.append(f"{column} = ?")
            args.append(value)
    delta = next(d for key, _, d in PERIODS if key == period)
    if delta:
        where.append("datetime(occurred_at) >= datetime('now', ?)")
        args.append(delta)
    clause = " AND ".join(where) or "1=1"
    if view == "activity":
        sql = ("SELECT datetime(occurred_at), occurred_at, event_type, status, detail, message_id FROM log_entries "
               f"WHERE {clause} ORDER BY datetime(occurred_at) DESC, rowid DESC LIMIT ? OFFSET ?")
    else:
        sql = ("SELECT datetime(occurred_at), occurred_at, accessed_by, table_name, operation, record_id FROM audit_log "
               f"WHERE {clause} ORDER BY datetime(occurred_at) DESC, rowid DESC LIMIT ? OFFSET ?")
    rows = con.execute(sql, args + [PAGE_SIZE + 1, (page - 1) * PAGE_SIZE]).fetchall()
    has_next = len(rows) > PAGE_SIZE

    entries = []
    for r in rows[:PAGE_SIZE]:
        when = format_time(r[0], zone) or mask_text(r[1])
        if view == "activity":
            status = str(r[3])
            detail = mask_text(r[4] or "")
            entries.append({
                "when": when, "title": mask_text(r[2]), "extra": short(r[5]),
                "badge": "failed" if status == "failed" else "soft" if status in ("degraded", "ignored") else "plain",
                "label": "FAILED" if status == "failed" else mask_text(status),
                "text": detail[:MAX_DETAIL] + ("..." if len(detail) > MAX_DETAIL else "")})
        else:
            entries.append({"when": when, "who": mask_text(r[2]), "table": mask_text(r[3]),
                            "op": mask_text(r[4]), "record": short(r[5])})

    keep = {"view": view, "period": period}
    keep.update({f["name"]: f["value"] for f in filters if f["value"] != "all"})
    return {
        "view": view, "views": [(key, label, urlencode({"view": key})) for key, label in VIEWS],
        "period": period, "periods": [(key, label) for key, label, _ in PERIODS],
        "filters": filters, "entries": entries, "page": page,
        "prev_query": urlencode({**keep, "page": page - 1}) if page > 1 else None,
        "next_query": urlencode({**keep, "page": page + 1}) if has_next else None,
        "zone_name": getattr(zone, "key", "UTC")}
