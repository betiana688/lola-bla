#!/usr/bin/env python3
"""Start the Lola-Bla console over HTTPS. Run on the Pi:  python3 console/run.py
Port: $LOLA_CONSOLE_PORT (default 9443). Stop with Ctrl+C."""

import os
import socket
import sys

import uvicorn

from lola_console import tls, users
from lola_console.web import create_app


def main():
    port = int(os.environ.get("LOLA_CONSOLE_PORT", "9443"))
    cert, key = tls.TLS_DIR / "cert.pem", tls.TLS_DIR / "key.pem"
    if not (cert.exists() and key.exists()):
        sys.exit("No certificate yet. Create one first:  python3 console/manage.py make-cert")
    con = users.connect()
    try:
        if not con.execute("SELECT 1 FROM users").fetchone():
            sys.exit("No console user yet. Create one first:  python3 console/manage.py create-user")
    finally:
        con.close()
    with socket.socket() as probe:
        probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            probe.bind(("0.0.0.0", port))
        except OSError:
            sys.exit(f"Port {port} is already in use. Set LOLA_CONSOLE_PORT to another port.")
    print(f"Lola-Bla console: https://reachy-mini.local:{port}/")
    print(f"Certificate fingerprint (SHA-256): {tls.fingerprint(cert)}")
    print("Your browser will warn once that the certificate is self-signed. Stop with Ctrl+C.")
    uvicorn.run(create_app(allowed_hosts=tls.allowed_hosts()), host="0.0.0.0", port=port,
                ssl_keyfile=str(key), ssl_certfile=str(cert), server_header=False,
                access_log=False, log_level="info")


if __name__ == "__main__":
    main()
