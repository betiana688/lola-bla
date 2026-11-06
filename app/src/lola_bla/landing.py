"""A tiny plain-http page so Reachy Mini Control can reach the app's web address.

Control checks the app's web address with an http request after the app starts. The console
uses https with a self-signed certificate. This page has no login and no settings: the app
name, a short description and the way to the console. It never redirects.

It has two looks (decided from how Reachy Mini Control asks for it, see
docs/architecture/console-redesign.md): inside Control the link does nothing, so the page tells
the viewer to click Control's arrow icon; in a browser it shows a working button.

The link uses the address the viewer used to reach this page (for example the robot's IP address
shown by Control). The name reachy-mini.local can resolve to IPv6 on some networks, where the
console does not listen. The link opens in a new tab because the console refuses to be shown
inside another page (frame protection, on purpose).
"""

import base64
import hashlib
import html
import importlib.util
import ipaddress
import os
import re
import sqlite3
import threading
from urllib.parse import quote
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 9080
DEFAULT_CONSOLE_PORT = "9443"
FALLBACK_HOST = "reachy-mini.local"
LOGGED_REQUESTS = 15  # log only the first requests, so the journal does not flood

_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")
_IPV6 = re.compile(r"\[[0-9A-Fa-f:.]{2,45}\]")
_UNUSABLE = {"0.0.0.0", "[::]"}
# Diagnostic: how does Reachy Mini Control ask for this page? Never cookies or credentials.
LOGGED_HEADERS = ("Origin", "Referer", "Sec-Fetch-Dest", "Sec-Fetch-Mode", "Sec-Fetch-Site", "User-Agent")


def describe_headers(headers) -> str:
    """The few watched headers of a request, cleaned and shortened. Nothing else is ever logged."""
    parts = []
    for name in LOGGED_HEADERS:
        value = headers.get(name)
        if value:
            clean = "".join(c if c.isprintable() else "?" for c in value)[:120]
            parts.append(f"{name}={clean}")
    return " | ".join(parts) or "(none of the watched headers)"


def port_from_env() -> int:
    return int(os.environ.get("LOLA_LANDING_PORT", DEFAULT_PORT))


def console_port() -> str:
    value = os.environ.get("LOLA_CONSOLE_PORT", DEFAULT_CONSOLE_PORT)
    return value if value.isdigit() else DEFAULT_CONSOLE_PORT


def usable_ip(value):
    """The address this server was reached on, if it is a real network address, else None."""
    try:
        ip = ipaddress.ip_address(str(value))
    except ValueError:
        return None
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_link_local:
        return None
    return f"[{ip}]" if ip.version == 6 else str(ip)


def viewer_host(header, local_ip=None) -> str:
    """Where to send the viewer: the address this server was reached on (it always works, it is
    never the viewer's text), else the Host header if it looks right, else the fallback name."""
    ip = usable_ip(local_ip)
    if ip:
        return ip
    if not header or len(header) > 260:
        return FALLBACK_HOST
    text = header.strip()
    if text.startswith("["):
        end = text.find("]")
        host = text[: end + 1] if end != -1 else ""
        valid = bool(_IPV6.fullmatch(host))
    else:
        host = text.rsplit(":", 1)[0] if ":" in text else text
        valid = bool(_NAME.fullmatch(host))
    if not valid or host in _UNUSABLE:
        return FALLBACK_HOST
    return host


def console_url(host_header=None, local_ip=None) -> str:
    return f"https://{viewer_host(host_header, local_ip)}:{console_port()}/"


EMBEDDED_REFERERS = ("http://tauri.localhost", "https://tauri.localhost", "tauri://localhost")
ASSETS = {  # the only other things this server hands out: the brand fonts and the mark
    "/fonts/Fraunces.ttf": ("fonts/Fraunces.ttf", "font/ttf"),
    "/fonts/DMMono-Regular.ttf": ("fonts/DMMono-Regular.ttf", "font/ttf"),
    "/fonts/DMMono-Medium.ttf": ("fonts/DMMono-Medium.ttf", "font/ttf"),
    "/mark.svg": ("lola-bla-mark.svg", "image/svg+xml"),
}
DESCRIPTION = "Lola hears and answers Signal voice messages."
# The one script on this page: it selects the address and copies it. No network, no data.
SCRIPT = ("document.getElementById('copy').onclick=function(){var a=document.getElementById('addr'),"
          "r=document.createRange(),s=getSelection(),ok=false;r.selectNodeContents(a);s.removeAllRanges();"
          "s.addRange(r);try{ok=document.execCommand('copy')}catch(e){}"
          "this.textContent=ok?'copied \u2713':'press Ctrl+C'};")

CSS = """
@font-face { font-family: "Fraunces"; src: url("/fonts/Fraunces.ttf") format("truetype"); font-weight: 100 900; font-display: swap; }
@font-face { font-family: "DM Mono"; src: url("/fonts/DMMono-Regular.ttf") format("truetype"); font-weight: 400; font-display: swap; }
@font-face { font-family: "DM Mono"; src: url("/fonts/DMMono-Medium.ttf") format("truetype"); font-weight: 500; font-display: swap; }
:root {
  color-scheme: light dark;
  --banana: #F7D33E; --violeta: #7B4FC4; --berenjena: #2A1640; --crema: #FFF8E7;
  --page: #C9B3F2; --card: #FFF8E7; --ink: #2A1640; --muted: #5A4675; --link: #7B4FC4;
  --btn-bg: #7B4FC4; --btn-text: #FFF8E7; --header-bg: #F7D33E; --header-ink: #2A1640;
  --chip-bg: #F7D33E; --chip-ink: #2A1640;
  --font-display: "Fraunces", Georgia, serif; --font-mono: "DM Mono", ui-monospace, monospace;
}
@media (prefers-color-scheme: dark) {
  :root { --page: #1E0F30; --card: #2A1640; --ink: #FFF8E7; --muted: #CDBFE3; --link: #FFF8E7; }
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--page); color: var(--ink); font-family: var(--font-mono); font-size: 18px; line-height: 1.6; }
header { display: flex; align-items: center; gap: 12px; padding: 10px 20px; background: var(--header-bg); color: var(--header-ink); border-bottom: 3px solid var(--header-ink); }
header img { width: 48px; height: 48px; display: block; }
.word { font-family: var(--font-display); font-weight: 900; font-size: 1.9rem; letter-spacing: -0.04em; line-height: 1; }
main { width: calc(100% - 32px); max-width: 38rem; margin: 1.5rem auto; padding: 28px; background: var(--card); border: 5px solid var(--ink); border-radius: 32px; }
h1 { font-family: var(--font-display); font-weight: 900; font-size: 2.2rem; line-height: 1.05; letter-spacing: -0.03em; margin: 0 0 0.5em; }
h1 em { font-style: normal; font-weight: 600; color: var(--link); }
h2 { font-size: 1rem; font-weight: 500; letter-spacing: 0.08em; margin: 1.6rem 0 0.4rem; }
p { margin: 0.6rem 0; }
.chip { display: inline-block; padding: 0.15rem 0.9rem; font-weight: 500; letter-spacing: 0.04em; background: var(--chip-bg); color: var(--chip-ink); border: 3px solid var(--ink); border-radius: 999px; }
.button { display: inline-flex; align-items: center; min-height: 52px; padding: 0.5rem 1.5rem; font-weight: 500; letter-spacing: 0.04em; text-decoration: none; background: var(--btn-bg); color: var(--btn-text); border: 5px solid var(--ink); border-radius: 999px; }
.button:hover { background: var(--berenjena); }
.address { font-weight: 500; word-break: break-all; }
.muted { color: var(--muted); }
button.copy { font: inherit; font-size: 0.9rem; min-height: 40px; padding: 0.2rem 1rem; background: var(--card); color: var(--ink); border: 3px solid var(--ink); border-radius: 999px; cursor: pointer; }
button.copy:hover { background: var(--banana); color: var(--berenjena); }
:focus-visible { outline: 4px solid var(--ink); outline-offset: 3px; }
"""


def variant(referer) -> str:
    """'embedded' (shown inside Reachy Mini Control), 'browser' (no Referer) or 'other'."""
    if not referer:
        return "browser"
    return "embedded" if referer.strip().startswith(EMBEDDED_REFERERS) else "other"


def signal_line(signal_linked) -> str:
    """One line about the Signal link. Hidden while unknown. Never shows a phone number."""
    if signal_linked is None:
        return ""
    word = "linked" if signal_linked else "not linked yet"
    return f'<h2>signal</h2><p><span class="chip">{word}</span></p>'


def page(host_header=None, referer=None, signal_linked=None, local_ip=None) -> bytes:
    url = html.escape(console_url(host_header, local_ip), quote=True)
    safe = "<p>one more click, for your safety: settings live on a password-protected page and open in a safe tab.</p>"
    button = (f'<p><a class="button" href="{url}" target="_blank" rel="noopener noreferrer">'
              "open settings</a></p>")
    where = ('<p class="muted">or paste this in your browser:<br>'
             f'<span class="address" id="addr">{url}</span> <button type="button" class="copy" id="copy">copy</button></p>')
    arrow = ("<p>settings are protected by a password, so they open in your browser, a safe place. "
             "Two quick clicks: the <b>arrow icon</b> at the top right, then <b>open settings</b>. \u2665</p>")
    embedded = variant(referer) == "embedded"
    way = arrow if embedded else safe + button + where
    script = "" if embedded else f"<script>{SCRIPT}</script>"
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Lola-Bla</title>'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<style>{CSS}</style></head><body>"
        '<header><img src="/mark.svg" alt=""><span class="word">Lola-Bla</span></header>'
        f"<main><h1>talk to abuelo <em>without a phone.</em></h1><p>{html.escape(DESCRIPTION)}</p>"
        f"{signal_line(signal_linked)}{way}</main>{script}</body></html>"
    ).encode("utf-8")


def asset_dir():
    """The console's static folder (brand fonts and mark are kept in one place), or None."""
    spec = importlib.util.find_spec("lola_console")
    folders = list(spec.submodule_search_locations or []) if spec else []
    return Path(folders[0]) / "static" if folders else None


def asset(path):
    """(bytes, content type) for one of the few allowed asset paths, else None."""
    entry = ASSETS.get(path.split("?", 1)[0])
    folder = asset_dir()
    if not entry or folder is None:
        return None
    try:
        return (folder / entry[0]).read_bytes(), entry[1]
    except OSError:
        return None


SCRIPT_HASH = base64.b64encode(hashlib.sha256(SCRIPT.encode()).digest()).decode()
CSP = (f"default-src 'none'; style-src 'unsafe-inline'; font-src 'self'; img-src 'self'; "
       f"script-src 'sha256-{SCRIPT_HASH}'")


DEFAULT_DB = Path.home() / "lola-bla-agents" / "reachy_mini_conversation_app" / "local_data" / "lola.db"


def signal_status(path=None):
    """Is the robot linked to Signal? True, False, or None when it cannot be read.
    Read-only connection, one fixed query, a yes or no. The phone number is never selected."""
    path = Path(path or os.environ.get("LOLA_DB", str(DEFAULT_DB)))
    try:
        con = sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True, timeout=1)
        try:
            row = con.execute("SELECT status FROM accounts LIMIT 1").fetchone()
        finally:
            con.close()
    except (sqlite3.Error, OSError):
        return None
    return bool(row and row[0] == "linked")


class Handler(BaseHTTPRequestHandler):
    server_version = "Lola-Bla"
    sys_version = ""

    def _send(self, body, ctype, cache) -> None:
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", CSP)
        self.end_headers()

    def _answer(self, with_body: bool) -> None:
        found = asset(self.path)
        if found:
            body, ctype = found
            self._send(body, ctype, "max-age=3600")
        else:
            self.server.request_count = getattr(self.server, "request_count", 0) + 1
            if self.server.request_count <= LOGGED_REQUESTS:
                print(f"[lola_bla] landing page: {self.command} from {self.client_address[0]}", flush=True)
                print(f"[lola_bla] landing page headers: {describe_headers(self.headers)}", flush=True)
            body = page(self.headers.get("Host"), self.headers.get("Referer"), signal_status(),
                        self.connection.getsockname()[0])
            ctype = "text/html; charset=utf-8"
            self._send(body, ctype, "no-store")
        if with_body:
            self.wfile.write(body)

    def do_GET(self) -> None:
        self._answer(True)

    def do_HEAD(self) -> None:
        self._answer(False)

    def log_message(self, *args) -> None:
        pass


def serve(stop_event, port=None, host="0.0.0.0", on_ready=None) -> None:
    """Serve the page until stop_event is set. Raises OSError if the port is busy."""
    server = ThreadingHTTPServer((host, port_from_env() if port is None else port), Handler)
    server.daemon_threads = True
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2},
                              name="lola-landing", daemon=True)
    thread.start()
    try:
        if on_ready:
            on_ready(server.server_address[1])
        stop_event.wait()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
