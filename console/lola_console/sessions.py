"""Signed cookies for the console. Standard library only (HMAC-SHA256).
A token is bound to a purpose ("session" or "login"), so one kind cannot be used as the other."""

import base64
import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

SESSION_SECONDS = 8 * 3600
KEY_PATH = Path.home() / ".config" / "lola-bla" / "console_secret.key"


def load_or_create_secret(path=KEY_PATH) -> bytes:
    """The signing key, created once (owner-only). Replacing it signs everyone out."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.parent.chmod(0o700)
    if path.exists():
        data = path.read_bytes()
        if len(data) >= 32:
            return data
    key = secrets.token_bytes(32)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key)
    path.chmod(0o600)
    return key


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Signer:
    def __init__(self, secret: bytes):
        if len(secret) < 16:
            raise ValueError("secret too short")
        self.secret = secret

    def _mac(self, purpose: str, body: bytes) -> bytes:
        return hmac.new(self.secret, purpose.encode("ascii") + b"." + body, hashlib.sha256).digest()

    def dumps(self, purpose: str, payload: dict) -> str:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return _b64(body) + "." + _b64(self._mac(purpose, body))

    def loads(self, purpose: str, token):
        """The payload if the token is genuine and for this purpose, otherwise None."""
        try:
            body_b64, mac_b64 = token.split(".")
            body, mac = _unb64(body_b64), _unb64(mac_b64)
            if not hmac.compare_digest(mac, self._mac(purpose, body)):
                return None
            data = json.loads(body)
            return data if isinstance(data, dict) else None
        except Exception:
            return None
