#!/usr/bin/env python3
"""Start the Lola-Bla console over HTTPS. Run on the Pi:  python3 console/run.py
Port: $LOLA_CONSOLE_PORT (default 9443). Stop with Ctrl+C."""

import signal
import sys
import threading

from lola_console import server, tls


def main():
    stop = threading.Event()
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, lambda *_: stop.set())
    port = server.port_from_env()

    def announce():
        print(f"Lola-Bla console: https://reachy-mini.local:{port}/")
        print(f"Certificate fingerprint (SHA-256): {tls.fingerprint(tls.TLS_DIR / 'cert.pem')}")
        print("Your browser will warn once that the certificate is self-signed. Stop with Ctrl+C.")

    try:
        server.serve(stop, port=port, on_ready=announce)
    except server.ServeError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
