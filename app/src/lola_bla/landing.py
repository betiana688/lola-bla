"""A tiny plain-http page so Reachy Mini Control can reach the app's web address.

Control checks the app's web address with an http request after the app starts. The console
uses https with a self-signed certificate. This page has no data, no login and no settings:
only the app name and a link to the console. It never redirects.

The link uses the address the viewer used to reach this page (for example the robot's IP address
shown by Control). The name reachy-mini.local can resolve to IPv6 on some networks, where the
console does not listen. The link opens in a new tab because the console refuses to be shown
inside another page (frame protection, on purpose).
"""

import html
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 9080
DEFAULT_CONSOLE_PORT = "9443"
FALLBACK_HOST = "reachy-mini.local"
LOGGED_REQUESTS = 15  # log only the first requests, so the journal does not flood

_NAME = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9.-]{0,251}[A-Za-z0-9])?")
_IPV6 = re.compile(r"\[[0-9A-Fa-f:.]{2,45}\]")
_UNUSABLE = {"0.0.0.0", "[::]"}


def port_from_env() -> int:
    return int(os.environ.get("LOLA_LANDING_PORT", DEFAULT_PORT))


def console_port() -> str:
    value = os.environ.get("LOLA_CONSOLE_PORT", DEFAULT_CONSOLE_PORT)
    return value if value.isdigit() else DEFAULT_CONSOLE_PORT


def viewer_host(header) -> str:
    """The host name or IP address from the Host header, or the fallback if it looks wrong."""
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


def console_url(host_header=None) -> str:
    return f"https://{viewer_host(host_header)}:{console_port()}/"


def page(host_header=None) -> bytes:
    url = html.escape(console_url(host_header), quote=True)
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Lola-Bla</title>'
        '<meta name="viewport" content="width=device-width, initial-scale=1"></head>'
        '<body style="font-family:sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem">'
        "<h1>Lola-Bla is running</h1>"
        f'<p><a href="{url}" target="_blank" rel="noopener noreferrer">Open the family console</a></p>'
        f'<p style="color:#555">If nothing opens, type this address in your browser:<br><b>{url}</b></p>'
        "</body></html>"
    ).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "Lola-Bla"
    sys_version = ""

    def _answer(self, with_body: bool) -> None:
        self.server.request_count = getattr(self.server, "request_count", 0) + 1
        if self.server.request_count <= LOGGED_REQUESTS:
            print(f"[lola_bla] landing page: {self.command} from {self.client_address[0]}", flush=True)
        body = page(self.headers.get("Host"))
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", "default-src 'none'; style-src 'unsafe-inline'")
        self.end_headers()
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
