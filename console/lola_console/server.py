"""Run the console over HTTPS from inside another program, for example a Reachy Mini app.
serve() blocks until stop_event is set, then shuts the console down and frees the port.
It raises ServeError with a plain message when the console cannot start."""

import os
import socket
import threading
from pathlib import Path

import uvicorn

from . import tls, users
from .web import create_app


class ServeError(RuntimeError):
    """The console cannot start. The message says what to fix."""


def port_from_env():
    return int(os.environ.get("LOLA_CONSOLE_PORT", "9443"))


def check_ready(port, tls_dir=None, db_path=None, host="0.0.0.0"):
    """Check the certificate, the console user and the port. Returns (cert, key) paths."""
    tls_dir = Path(tls_dir) if tls_dir else tls.TLS_DIR
    cert, key = tls_dir / "cert.pem", tls_dir / "key.pem"
    if not (cert.exists() and key.exists()):
        raise ServeError("No certificate yet. Create one first:  python3 console/manage.py make-cert")
    con = users.connect(db_path) if db_path else users.connect()
    try:
        if not con.execute("SELECT 1 FROM users").fetchone():
            raise ServeError("No console user yet. Create one first:  python3 console/manage.py create-user")
    finally:
        con.close()
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind((host, port))
        except OSError:
            raise ServeError(f"Port {port} is already in use. Set LOLA_CONSOLE_PORT to another port.")
    return cert, key


def serve(stop_event, port=None, tls_dir=None, db_path=None, allowed_hosts=None, secret=None,
          host="0.0.0.0", on_ready=None, log_level="info"):
    port = port or port_from_env()
    cert, key = check_ready(port, tls_dir, db_path, host)
    hosts = allowed_hosts if allowed_hosts is not None else tls.allowed_hosts()
    app = create_app(db_path=db_path, secret=secret, allowed_hosts=hosts)
    config = uvicorn.Config(app, host=host, port=port, ssl_keyfile=str(key), ssl_certfile=str(cert),
                            server_header=False, access_log=False, log_level=log_level)
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # we are not on the main thread; the caller owns signals
    thread = threading.Thread(target=server.run, name="lola-console", daemon=True)
    thread.start()
    announced = False
    try:
        while not stop_event.wait(0.2):
            if not thread.is_alive():
                raise ServeError("The console stopped unexpectedly. See the messages above.")
            if on_ready and not announced and server.started:
                announced = True
                on_ready()
    finally:
        server.should_exit = True
        thread.join(timeout=10)
