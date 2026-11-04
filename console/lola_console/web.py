"""The Lola-Bla console web app: sign-in, sign-out and a home page. Starlette only.
State-changing requests are POSTs with a CSRF token and an Origin check. Sessions are signed
cookies that stop working when the password changes. The typed username is never stored."""

import asyncio
import hmac
import logging
import math
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import quote
from pathlib import Path

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.responses import JSONResponse, PlainTextResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from . import auth, contactadmin, groupadmin, link, signal_api, users
from .sessions import SESSION_SECONDS, Signer, load_or_create_secret

BASE = Path(__file__).parent
logger = logging.getLogger("lola_console")
templates = Jinja2Templates(directory=str(BASE / "templates"))

MAX_FAILED = 5
LOCK_MINUTES = 15
SESSION_COOKIE = "lola_session"
LOGIN_COOKIE = "lola_login"
LOGIN_COOKIE_SECONDS = 600
MAX_FIELD = 1024  # longest username or password we will even look at

HEADERS = {
    "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; "
                               "form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    # same-origin, not no-referrer: with no-referrer browsers send "Origin: null" on form posts,
    # which the origin check refuses. same-origin sends the real origin to this site only.
    "Referrer-Policy": "same-origin",
    "Cache-Control": "no-store",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
}
# No Strict-Transport-Security on purpose: with a self-signed certificate it would stop the
# browser from letting you accept the certificate.

_dummy_hash = None


class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        for key, value in HEADERS.items():
            response.headers[key] = value
        return response


def _dummy() -> str:
    """A real hash used when there is no user, so a missing user takes as long as a wrong password."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = auth.hash_password("timing-only-not-a-real-password")
    return _dummy_hash


def _connect(request):
    return users.connect(request.app.state.db_path)


def _parse_sql_time(text):
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).replace(tzinfo=timezone.utc).timestamp()
        except ValueError:
            continue
    return None


def _origin_ok(request) -> bool:
    origin = request.headers.get("origin")
    if origin is None:
        return True  # not a browser form post; the CSRF token and SameSite cookies still apply
    expected = f"{request.url.scheme}://{request.headers.get('host', '')}"
    if origin == expected:
        return True
    logger.warning("Refused a request: Origin %r does not match %r", origin[:100], expected[:100])
    return False


def _forbidden():
    return PlainTextResponse(
        "Forbidden: this request did not come from the console's own page. Reload the sign-in page and try again.",
        status_code=403)


def _set_cookie(response, name, value, seconds):
    response.set_cookie(name, value, max_age=seconds, path="/", secure=True, httponly=True, samesite="strict")


def _clear_cookie(response, name):
    response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="strict")


def _audit(con, who, user_id, operation):
    users._audit(con, who, user_id, operation)


def _activity(con, event_type, detail):
    con.execute("INSERT INTO log_entries (id, message_id, occurred_at, event_type, status, detail) "
                "VALUES (?, NULL, datetime('now'), ?, 'failed', ?)", (str(uuid.uuid4()), event_type, detail))


def _current_user(request):
    token = request.cookies.get(SESSION_COOKIE)
    data = request.app.state.signer.loads("session", token) if token else None
    if not data:
        return None
    try:
        iat, uid, csrf = float(data["iat"]), str(data["u"]), str(data["c"])
    except (KeyError, TypeError, ValueError):
        return None
    now = time.time()
    if not (now - SESSION_SECONDS < iat <= now + 60):
        return None
    con = _connect(request)
    try:
        row = con.execute("SELECT username, password_changed_at FROM users WHERE id = ?", (uid,)).fetchone()
    finally:
        con.close()
    if not row:
        return None
    changed = _parse_sql_time(row[1])
    if changed is not None and iat <= changed:
        return None  # signed in before the last password change
    return {"id": uid, "username": row[0], "csrf": csrf}


def _login_page(request, status=200, message=None):
    token = secrets.token_urlsafe(24)
    response = templates.TemplateResponse(request, "login.html", {"csrf": token, "message": message},
                                          status_code=status)
    signed = request.app.state.signer.dumps("login", {"t": token, "iat": time.time()})
    _set_cookie(response, LOGIN_COOKIE, signed, LOGIN_COOKIE_SECONDS)
    return response


async def login_get(request):
    if _current_user(request):
        return RedirectResponse("/", status_code=303)
    return _login_page(request)


async def login_post(request):
    if not _origin_ok(request):
        return _forbidden()
    form = await request.form()
    username = str(form.get("username", ""))[:MAX_FIELD].strip().lower()
    password = str(form.get("password", ""))
    sent = str(form.get("csrf", ""))
    cookie = request.cookies.get(LOGIN_COOKIE)
    data = request.app.state.signer.loads("login", cookie) if cookie else None
    token_ok = False
    if data and isinstance(data.get("t"), str):
        try:
            age = time.time() - float(data.get("iat", 0))
            token_ok = hmac.compare_digest(data["t"].encode(), sent.encode()) and 0 <= age < LOGIN_COOKIE_SECONDS
        except (TypeError, ValueError):
            token_ok = False
    if not token_ok:
        return _login_page(request, 403, "This page expired. Please try again.")

    con = _connect(request)
    try:
        row = con.execute("SELECT id, username, password_hash, failed_attempts, locked_until FROM users").fetchone()
        now = con.execute("SELECT strftime('%Y-%m-%d %H:%M:%f','now')").fetchone()[0]

        if row and row[4] and row[4] > now:
            with con:
                _audit(con, "console:anonymous", row[0], "blocked")
                _activity(con, "login_blocked", "A sign-in attempt was refused because sign-in is locked")
            minutes = max(1, math.ceil(((_parse_sql_time(row[4]) or time.time()) - time.time()) / 60))
            return _login_page(request, 429, f"Too many attempts. Sign-in is locked. Try again in about {minutes} minutes.")

        stored = row[2] if row else _dummy()
        password_ok = False
        if len(password) <= MAX_FIELD:
            password_ok = await run_in_threadpool(auth.verify_password, password, stored)
        name_ok = bool(row) and hmac.compare_digest(username.encode(), row[1].encode())

        if row and password_ok and name_ok:
            with con:
                con.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (row[0],))
                _audit(con, f"console:{row[1]}", row[0], "login_ok")
            response = RedirectResponse("/", status_code=303)
            session = {"u": row[0], "iat": time.time(), "c": secrets.token_urlsafe(24)}
            _set_cookie(response, SESSION_COOKIE, request.app.state.signer.dumps("session", session), SESSION_SECONDS)
            _clear_cookie(response, LOGIN_COOKIE)
            return response

        failed = (row[3] + 1) if row else 0
        locked = bool(row) and failed >= MAX_FAILED
        with con:
            if row and locked:
                con.execute("UPDATE users SET failed_attempts = ?, "
                            "locked_until = strftime('%Y-%m-%d %H:%M:%f','now', ?) WHERE id = ?",
                            (failed, f"+{LOCK_MINUTES} minutes", row[0]))
            elif row:
                con.execute("UPDATE users SET failed_attempts = ? WHERE id = ?", (failed, row[0]))
            _audit(con, "console:anonymous", row[0] if row else None, "login_failed")
            if locked:
                _audit(con, "console:anonymous", row[0], "locked")
                _activity(con, "login_locked", f"Sign-in locked for {LOCK_MINUTES} minutes after {MAX_FAILED} wrong attempts")
            elif row:
                _activity(con, "login_failed", f"Wrong sign-in attempt ({failed} in a row)")
            else:
                _activity(con, "login_failed", "Sign-in attempt, but no user is set up")
        if locked:
            return _login_page(request, 429, f"Too many attempts. Sign-in is locked for {LOCK_MINUTES} minutes.")
        return _login_page(request, 401, "Wrong username or password.")
    finally:
        con.close()


async def home(request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    notice = "Password changed. Any other sign-ins have ended." if request.query_params.get("notice") == "password_changed" else None
    con = _connect(request)
    try:
        account = con.execute("SELECT status FROM accounts LIMIT 1").fetchone()
        groups = con.execute("SELECT COUNT(*) FROM groups WHERE is_active = 1").fetchone()[0]
        contacts = con.execute("SELECT COUNT(*) FROM contacts").fetchone()[0]
        failures = con.execute("SELECT COUNT(*) FROM log_entries WHERE status = 'failed' "
                               "AND occurred_at > datetime('now', '-1 day')").fetchone()[0]
    finally:
        con.close()
    return templates.TemplateResponse(request, "home.html", {
        "username": user["username"], "csrf": user["csrf"],
        "account_status": account[0] if account else "none",
        "groups": groups, "contacts": contacts, "failures": failures, "notice": notice})


async def logout(request):
    if not _origin_ok(request):
        return _forbidden()
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    if not hmac.compare_digest(str(form.get("csrf", "")).encode(), user["csrf"].encode()):
        return _forbidden()
    con = _connect(request)
    try:
        with con:
            _audit(con, f"console:{user['username']}", user["id"], "logout")
    finally:
        con.close()
    response = RedirectResponse("/login", status_code=303)
    _clear_cookie(response, SESSION_COOKIE)
    return response


def _password_page(request, user, status=200, message=None):
    return templates.TemplateResponse(
        request, "password.html",
        {"username": user["username"], "csrf": user["csrf"], "message": message,
         "min_length": auth.MIN_PASSWORD_LENGTH}, status_code=status)


async def password_get(request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    return _password_page(request, user)


async def password_post(request):
    if not _origin_ok(request):
        return _forbidden()
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    if not hmac.compare_digest(str(form.get("csrf", "")).encode(), user["csrf"].encode()):
        return _forbidden()
    current = str(form.get("current", ""))
    new = str(form.get("new", ""))
    repeat = str(form.get("repeat", ""))
    who = f"console:{user['username']}"

    con = _connect(request)
    try:
        row = con.execute("SELECT password_hash, failed_attempts, locked_until FROM users WHERE id = ?",
                          (user["id"],)).fetchone()
        if not row:
            return RedirectResponse("/login", status_code=303)
        now = con.execute("SELECT strftime('%Y-%m-%d %H:%M:%f','now')").fetchone()[0]

        if row[2] and row[2] > now:
            with con:
                _audit(con, who, user["id"], "blocked")
                _activity(con, "password_change_blocked", "A password change was refused because sign-in is locked")
            minutes = max(1, math.ceil(((_parse_sql_time(row[2]) or time.time()) - time.time()) / 60))
            return _password_page(request, user, 429,
                                  f"Too many wrong passwords. This is locked for about {minutes} more minutes.")

        current_ok = len(current) <= MAX_FIELD and await run_in_threadpool(auth.verify_password, current, row[0])
        if not current_ok:
            failed = row[1] + 1
            locked = failed >= MAX_FAILED
            with con:
                if locked:
                    con.execute("UPDATE users SET failed_attempts = ?, "
                                "locked_until = strftime('%Y-%m-%d %H:%M:%f','now', ?) WHERE id = ?",
                                (failed, f"+{LOCK_MINUTES} minutes", user["id"]))
                else:
                    con.execute("UPDATE users SET failed_attempts = ? WHERE id = ?", (failed, user["id"]))
                _audit(con, who, user["id"], "password_change_failed")
                if locked:
                    _audit(con, who, user["id"], "locked")
                    _activity(con, "login_locked",
                              f"Sign-in locked for {LOCK_MINUTES} minutes after {MAX_FAILED} wrong passwords")
                else:
                    _activity(con, "password_change_failed",
                              f"Wrong current password when changing the password ({failed} in a row)")
            if locked:
                return _password_page(request, user, 429,
                                      f"Too many wrong passwords. Locked for {LOCK_MINUTES} minutes.")
            return _password_page(request, user, 401, "The current password is wrong.")

        problems = []
        if new != repeat:
            problems.append("the two new passwords do not match")
        problems += auth.check_password(new, user["username"])
        if new == current:
            problems.append("the new password must be different from the current one")
        if problems:
            return _password_page(request, user, 400, "Not changed: " + "; ".join(problems) + ".")

        new_hash = await run_in_threadpool(auth.hash_password, new)
        with con:
            con.execute(f"UPDATE users SET password_hash = ?, password_changed_at = {users.NOW}, "
                        "failed_attempts = 0, locked_until = NULL WHERE id = ?", (new_hash, user["id"]))
            _audit(con, who, user["id"], "password_changed")
        changed = _parse_sql_time(con.execute("SELECT password_changed_at FROM users WHERE id = ?",
                                              (user["id"],)).fetchone()[0])
        # A password change ends every sign-in, including this one. Issue a fresh session
        # (with a new CSRF token) that is clearly newer than the change.
        iat = max(time.time(), (changed or 0) + 0.001)
        response = RedirectResponse("/?notice=password_changed", status_code=303)
        session = {"u": user["id"], "iat": iat, "c": secrets.token_urlsafe(24)}
        _set_cookie(response, SESSION_COOKIE, request.app.state.signer.dumps("session", session), SESSION_SECONDS)
        return response
    finally:
        con.close()


LABELS = {"linked": "Linked", "not_linked": "Not linked", "removed": "Removed from Signal",
          "different": "A different account", "unknown": "Cannot tell",
          "unfinished": "Unlinking not finished"}

UNLINK_INFO = {
    "unlink": ("Unlink", "Unlinking stops the robot using your Signal account: Reachy will say it cannot reach "
                         "messages, and the app's local Signal data is deleted. Your Signal account itself is not "
                         "touched. Afterwards, remove 'reachy-mini' from Linked devices in Signal on your phone."),
    "cleanup": ("Clean up", "The robot's device is no longer linked on Signal's side. Cleaning up marks the robot "
                            "as unlinked and deletes the app's local Signal data."),
    "finish": ("Finish unlinking", "An earlier unlinking did not finish. This runs the remaining steps."),
}


def _csrf_ok(user, form) -> bool:
    return hmac.compare_digest(str(form.get("csrf", "")).encode(), user["csrf"].encode())


def _link_active(app):
    """The link in progress, or None. A link that ran out of time is dropped here."""
    state = app.state.link
    if state and time.time() - state["started"] > link.LINK_WINDOW_S:
        app.state.link = None
        app.state.flash = "The link code expired. Start again if you still want to link."
        return None
    return state


def _read_status_sync(db_path, api, device_name):
    con = users.connect(db_path)
    try:
        return link.read_status(con, api, device_name)
    finally:
        con.close()


def _finish_link_sync(db_path, api, user, device_name):
    con = users.connect(db_path)
    try:
        return link.finish_link(con, api, user["id"], f"console:{user['username']}", device_name)
    finally:
        con.close()


async def signal_get(request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    app = request.app
    status = await run_in_threadpool(_read_status_sync, app.state.db_path, app.state.signal, app.state.device_name)
    state = _link_active(app)
    flash, app.state.flash = app.state.flash, None
    minutes_left = max(1, math.ceil((link.LINK_WINDOW_S - (time.time() - state["started"])) / 60)) if state else 0
    return templates.TemplateResponse(request, "signal.html", {
        "status": status, "label": LABELS[status["state"]], "linking": bool(state),
        "csrf": user["csrf"], "flash": flash, "minutes_left": minutes_left,
        "unlink_info": UNLINK_INFO.get(status.get("unlink"))})


async def link_start(request):
    if not _origin_ok(request):
        return _forbidden()
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    if not _csrf_ok(user, form):
        return _forbidden()
    app = request.app
    if _link_active(app):
        return RedirectResponse("/signal", status_code=303)
    status = await run_in_threadpool(_read_status_sync, app.state.db_path, app.state.signal, app.state.device_name)
    if not status["can_link"]:
        app.state.flash = "Linking is not possible right now: " + status["message"]
        return RedirectResponse("/signal", status_code=303)
    try:
        png = await run_in_threadpool(app.state.signal.qr_png, app.state.device_name)
    except signal_api.SignalApiError as e:
        app.state.flash = f"Could not get a link code from the Signal API ({e}). Nothing was changed."
        return RedirectResponse("/signal", status_code=303)
    app.state.link = {"png": png, "started": time.time()}
    con = _connect(request)
    try:
        with con:
            link.audit(con, f"console:{user['username']}", "accounts", None, "link_started")
    finally:
        con.close()
    return RedirectResponse("/signal", status_code=303)


async def link_qr(request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    state = _link_active(request.app)
    if not state:
        return PlainTextResponse("Not found", status_code=404)
    return Response(state["png"], media_type="image/png")


async def link_check(request):
    app = request.app
    if not _origin_ok(request):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    user = _current_user(request)
    if not user:
        return JSONResponse({"error": "signed out"}, status_code=401)
    form = await request.form()
    if not _csrf_ok(user, form):
        return JSONResponse({"error": "forbidden"}, status_code=403)
    async with app.state.link_lock:
        if not _link_active(app):
            return JSONResponse({"done": True, "expired": True})
        outcome, text = await run_in_threadpool(
            _finish_link_sync, app.state.db_path, app.state.signal, user, app.state.device_name)
        if outcome == "waiting":
            return JSONResponse({"done": False})
        app.state.link = None
        app.state.flash = "Linked. The robot's Signal device is set up." if outcome == "linked" else text
        return JSONResponse({"done": True, "ok": outcome == "linked"})


async def link_cancel(request):
    if not _origin_ok(request):
        return _forbidden()
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    if not _csrf_ok(user, form):
        return _forbidden()
    if request.app.state.link:
        request.app.state.link = None
        con = _connect(request)
        try:
            with con:
                link.audit(con, f"console:{user['username']}", "accounts", None, "link_cancelled")
        finally:
            con.close()
    return RedirectResponse("/signal", status_code=303)


UNLINK_WORD = "UNLINK"


async def _reauthenticate(con, user, password, who, what="unlink"):
    """Ask for the password again before something important. A wrong password counts toward the
    same lockout as sign-in. Returns None if the password is right, otherwise a message to show."""
    row = con.execute("SELECT password_hash, failed_attempts, locked_until FROM users WHERE id = ?",
                      (user["id"],)).fetchone()
    if not row:
        return "You are not signed in."
    now = con.execute("SELECT strftime('%Y-%m-%d %H:%M:%f','now')").fetchone()[0]
    if row[2] and row[2] > now:
        with con:
            _audit(con, who, user["id"], "blocked")
            _activity(con, f"{what}_blocked", f"A {what} was refused because sign-in is locked")
        return "Too many wrong passwords. This is locked for a while."
    ok = len(password) <= MAX_FIELD and await run_in_threadpool(auth.verify_password, password, row[0])
    if ok:
        with con:
            con.execute("UPDATE users SET failed_attempts = 0, locked_until = NULL WHERE id = ?", (user["id"],))
        return None
    failed = row[1] + 1
    locked = failed >= MAX_FAILED
    with con:
        if locked:
            con.execute("UPDATE users SET failed_attempts = ?, "
                        "locked_until = strftime('%Y-%m-%d %H:%M:%f','now', ?) WHERE id = ?",
                        (failed, f"+{LOCK_MINUTES} minutes", user["id"]))
        else:
            con.execute("UPDATE users SET failed_attempts = ? WHERE id = ?", (failed, user["id"]))
        _audit(con, who, user["id"], f"{what}_password_failed")
        if locked:
            _audit(con, who, user["id"], "locked")
            _activity(con, "login_locked", f"Sign-in locked for {LOCK_MINUTES} minutes after {MAX_FAILED} wrong passwords")
        else:
            _activity(con, f"{what}_password_failed", f"Wrong password when trying to {what} ({failed} in a row)")
    return f"Too many wrong passwords. Locked for {LOCK_MINUTES} minutes." if locked else "The password is wrong."


def _unlink_sync(db_path, api, who):
    con = users.connect(db_path)
    try:
        return link.unlink(con, api, who)
    finally:
        con.close()


async def unlink_post(request):
    if not _origin_ok(request):
        return _forbidden()
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    form = await request.form()
    if not _csrf_ok(user, form):
        return _forbidden()
    app = request.app
    who = f"console:{user['username']}"

    def back(message):
        app.state.flash = message
        return RedirectResponse("/signal", status_code=303)

    if str(form.get("confirm", "")).strip() != UNLINK_WORD:
        return back(f"Nothing was done. Type {UNLINK_WORD} in capital letters to confirm.")
    if _link_active(app):
        return back("A link is in progress. Cancel it first.")
    con = _connect(request)
    try:
        problem = await _reauthenticate(con, user, str(form.get("password", "")), who)
    finally:
        con.close()
    if problem:
        return back(problem)
    async with app.state.link_lock:
        outcome, text = await run_in_threadpool(_unlink_sync, app.state.db_path, app.state.signal, who)
    return back(text)


GROUP_REMOVE_WORD = "REMOVE"


def _with_con(db_path, fn, *args):
    con = users.connect(db_path)
    try:
        return fn(con, *args)
    finally:
        con.close()


def _group_redirect(app, message, target="/groups"):
    app.state.flash = message
    return RedirectResponse(target, status_code=303)


async def _group_post(request):
    """The checks every group action starts with: origin, signed in, CSRF token."""
    if not _origin_ok(request):
        return None, None, _forbidden()
    user = _current_user(request)
    if not user:
        return None, None, RedirectResponse("/login", status_code=303)
    form = await request.form()
    if not _csrf_ok(user, form):
        return None, None, _forbidden()
    return user, form, None


async def groups_get(request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    app = request.app
    items = await run_in_threadpool(_with_con, app.state.db_path, groupadmin.list_groups)
    flash, app.state.flash = app.state.flash, None
    return templates.TemplateResponse(request, "groups.html", {
        "groups": items, "csrf": user["csrf"], "flash": flash, "remove_word": GROUP_REMOVE_WORD})


async def groups_add_get(request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    app = request.app
    query = str(request.query_params.get("q", ""))[:60]
    result = await run_in_threadpool(_with_con, app.state.db_path, groupadmin.available_from_signal,
                                     app.state.signal, query)
    flash, app.state.flash = app.state.flash, None
    return templates.TemplateResponse(request, "groups_add.html", {
        "items": result["items"], "message": result["message"], "q": query,
        "csrf": user["csrf"], "flash": flash})


async def groups_add_post(request):
    user, form, error = await _group_post(request)
    if error:
        return error
    app = request.app
    try:
        await run_in_threadpool(_with_con, app.state.db_path, groupadmin.add_group, app.state.signal,
                                str(form.get("internal_id", ""))[:300], str(form.get("name", ""))[:200],
                                f"console:{user['username']}")
    except groupadmin.GroupError as e:
        return _group_redirect(app, str(e), "/groups/add")
    return _group_redirect(app, "Group added.")


async def groups_rename_post(request):
    user, form, error = await _group_post(request)
    if error:
        return error
    app = request.app
    try:
        await run_in_threadpool(_with_con, app.state.db_path, groupadmin.rename_group,
                                str(form.get("id", ""))[:60], str(form.get("name", ""))[:200],
                                f"console:{user['username']}")
    except groupadmin.GroupError as e:
        return _group_redirect(app, str(e))
    return _group_redirect(app, "Name saved.")


async def groups_active_post(request):
    user, form, error = await _group_post(request)
    if error:
        return error
    app = request.app
    active = str(form.get("active", "")) == "1"
    try:
        await run_in_threadpool(_with_con, app.state.db_path, groupadmin.set_active,
                                str(form.get("id", ""))[:60], active, f"console:{user['username']}")
    except groupadmin.GroupError as e:
        return _group_redirect(app, str(e))
    return _group_redirect(app, "Group is active again." if active else "Group deactivated. Nothing was deleted.")


async def groups_remove_post(request):
    user, form, error = await _group_post(request)
    if error:
        return error
    app = request.app
    who = f"console:{user['username']}"
    if str(form.get("confirm", "")).strip() != GROUP_REMOVE_WORD:
        return _group_redirect(app, f"Nothing was removed. Type {GROUP_REMOVE_WORD} in capital letters to confirm.")
    con = _connect(request)
    try:
        problem = await _reauthenticate(con, user, str(form.get("password", "")), who, what="remove")
    finally:
        con.close()
    if problem:
        return _group_redirect(app, problem)
    audio_dir = Path(app.state.db_path).parent / "audio"
    try:
        result = await run_in_threadpool(_with_con, app.state.db_path, groupadmin.remove_group,
                                         str(form.get("id", ""))[:60], who, audio_dir)
    except groupadmin.GroupError as e:
        return _group_redirect(app, str(e))
    return _group_redirect(app, groupadmin.removal_summary(result))


def _contacts_url(group_id, page="/contacts"):
    return page + "?group=" + quote(group_id, safe="")


def _back_to(form):
    group_id = str(form.get("group", ""))[:60]
    return _contacts_url(group_id) if group_id else "/groups"


async def contacts_get(request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    app = request.app
    group_id = str(request.query_params.get("group", ""))[:60]
    group = await run_in_threadpool(_with_con, app.state.db_path, contactadmin.group_info, group_id)
    if not group:
        return _group_redirect(app, "That group no longer exists.")
    items = await run_in_threadpool(_with_con, app.state.db_path, contactadmin.list_contacts, group_id)
    flash, app.state.flash = app.state.flash, None
    return templates.TemplateResponse(request, "contacts.html", {
        "group": group, "contacts": items, "csrf": user["csrf"], "flash": flash, "remove_word": GROUP_REMOVE_WORD})


async def contacts_add_get(request):
    user = _current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)
    app = request.app
    group_id = str(request.query_params.get("group", ""))[:60]
    query = str(request.query_params.get("q", ""))[:60]
    group = await run_in_threadpool(_with_con, app.state.db_path, contactadmin.group_info, group_id)
    if not group:
        return _group_redirect(app, "That group no longer exists.")
    result = await run_in_threadpool(_with_con, app.state.db_path, contactadmin.available_from_signal,
                                     app.state.signal, app.state.signer.secret, group_id, query)
    flash, app.state.flash = app.state.flash, None
    return templates.TemplateResponse(request, "contacts_add.html", {
        "group": group, "items": result["items"], "message": result["message"], "q": query,
        "csrf": user["csrf"], "flash": flash})


async def contacts_add_post(request):
    user, form, error = await _group_post(request)
    if error:
        return error
    app = request.app
    group_id = str(form.get("group", ""))[:60]
    try:
        await run_in_threadpool(_with_con, app.state.db_path, contactadmin.add_contact, app.state.signal,
                                app.state.signer.secret, group_id, str(form.get("ref", ""))[:100],
                                str(form.get("name", ""))[:200], f"console:{user['username']}")
    except groupadmin.GroupError as e:
        return _group_redirect(app, str(e), _contacts_url(group_id, "/contacts/add"))
    return _group_redirect(app, "Contact added.", _contacts_url(group_id))


async def contacts_rename_post(request):
    user, form, error = await _group_post(request)
    if error:
        return error
    app = request.app
    try:
        group_id = await run_in_threadpool(_with_con, app.state.db_path, contactadmin.rename_contact,
                                           str(form.get("id", ""))[:60], str(form.get("name", ""))[:200],
                                           f"console:{user['username']}")
    except groupadmin.GroupError as e:
        return _group_redirect(app, str(e), _back_to(form))
    return _group_redirect(app, "Name saved.", _contacts_url(group_id))


async def contacts_remove_post(request):
    user, form, error = await _group_post(request)
    if error:
        return error
    app = request.app
    who = f"console:{user['username']}"
    back = _back_to(form)
    if str(form.get("confirm", "")).strip() != GROUP_REMOVE_WORD:
        return _group_redirect(app, f"Nothing was removed. Type {GROUP_REMOVE_WORD} in capital letters to confirm.", back)
    con = _connect(request)
    try:
        problem = await _reauthenticate(con, user, str(form.get("password", "")), who, what="remove")
    finally:
        con.close()
    if problem:
        return _group_redirect(app, problem, back)
    audio_dir = Path(app.state.db_path).parent / "audio"
    try:
        result = await run_in_threadpool(_with_con, app.state.db_path, contactadmin.remove_contact,
                                         str(form.get("id", ""))[:60], who, audio_dir)
    except groupadmin.GroupError as e:
        return _group_redirect(app, str(e), back)
    return _group_redirect(app, contactadmin.removal_summary(result), _contacts_url(result["group_id"]))


def create_app(db_path=None, secret=None, allowed_hosts=None, signal_client=None, device_name=None):
    middleware = [Middleware(SecurityHeaders)]
    if allowed_hosts:
        middleware.insert(0, Middleware(TrustedHostMiddleware, allowed_hosts=list(allowed_hosts)))
    routes = [
        Route("/", home, methods=["GET"]),
        Route("/login", login_get, methods=["GET"]),
        Route("/login", login_post, methods=["POST"]),
        Route("/logout", logout, methods=["POST"]),
        Route("/password", password_get, methods=["GET"]),
        Route("/password", password_post, methods=["POST"]),
        Route("/signal", signal_get, methods=["GET"]),
        Route("/link/start", link_start, methods=["POST"]),
        Route("/link/qr.png", link_qr, methods=["GET"]),
        Route("/link/check", link_check, methods=["POST"]),
        Route("/link/cancel", link_cancel, methods=["POST"]),
        Route("/unlink", unlink_post, methods=["POST"]),
        Route("/groups", groups_get, methods=["GET"]),
        Route("/groups/add", groups_add_get, methods=["GET"]),
        Route("/groups/add", groups_add_post, methods=["POST"]),
        Route("/groups/rename", groups_rename_post, methods=["POST"]),
        Route("/groups/active", groups_active_post, methods=["POST"]),
        Route("/groups/remove", groups_remove_post, methods=["POST"]),
        Route("/contacts", contacts_get, methods=["GET"]),
        Route("/contacts/add", contacts_add_get, methods=["GET"]),
        Route("/contacts/add", contacts_add_post, methods=["POST"]),
        Route("/contacts/rename", contacts_rename_post, methods=["POST"]),
        Route("/contacts/remove", contacts_remove_post, methods=["POST"]),
        Mount("/static", StaticFiles(directory=str(BASE / "static")), name="static"),
    ]
    app = Starlette(routes=routes, middleware=middleware)
    app.state.db_path = Path(db_path) if db_path else users.db_path()
    app.state.signer = Signer(secret if secret is not None else load_or_create_secret())
    app.state.signal = signal_client if signal_client is not None else signal_api.SignalApi()
    app.state.device_name = device_name or os.environ.get("LOLA_DEVICE_NAME") or link.DEVICE_NAME
    app.state.link = None
    app.state.flash = None
    app.state.link_lock = asyncio.Lock()
    return app
