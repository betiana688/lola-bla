"""A tiny plain-http page so Reachy Mini Control can reach the app's web address.

Control checks the app's web address with an http request after the app starts. The console
uses https with a self-signed certificate. This page has no data, no login and no settings:
only the app name and a link to the console. It never redirects.
"""

import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DEFAULT_PORT = 9080
LOGGED_REQUESTS = 15  # log only the first requests, so the journal does not flood


def port_from_env() -> int:
    return int(os.environ.get("LOLA_LANDING_PORT", DEFAULT_PORT))


def console_url() -> str:
    return f"https://reachy-mini.local:{os.environ.get('LOLA_CONSOLE_PORT', '9443')}/"


def page() -> bytes:
    return (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Lola-Bla</title>'
        '<meta name="viewport" content="width=device-width, initial-scale=1"></head>'
        '<body style="font-family:sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem">'
        f'<h1>Lola-Bla is running</h1><p><a href="{console_url()}">Open the family console</a></p>'
        "</body></html>"
    ).encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    server_version = "Lola-Bla"
    sys_version = ""

    def _answer(self, with_body: bool) -> None:
        self.server.request_count = getattr(self.server, "request_count", 0) + 1
        if self.server.request_count <= LOGGED_REQUESTS:
            print(f"[lola_bla] landing page: {self.command} from {self.client_address[0]}", flush=True)
        body = page()
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
