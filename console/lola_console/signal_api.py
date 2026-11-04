"""A small client for the local signal-cli-rest-api. Standard library only.
Error messages never contain a phone number or a link code."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_URL = "http://localhost:8080"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
TIMEOUT_S = 60  # the Signal API does one operation at a time, so a call can wait behind another
MAX_BYTES = 2_000_000


class SignalApiError(Exception):
    """The Signal API could not be reached, or gave an answer we do not understand."""


class NotRegistered(SignalApiError):
    """The Signal API says this number is not registered."""


class SignalApi:
    def __init__(self, base_url=None, timeout=TIMEOUT_S):
        self.base = (base_url or os.environ.get("LOLA_SIGNAL_API", DEFAULT_URL)).rstrip("/")
        self.timeout = timeout

    def _get(self, path):
        try:
            with urllib.request.urlopen(self.base + path, timeout=self.timeout) as resp:
                return resp.read(MAX_BYTES)
        except urllib.error.HTTPError as e:
            body = e.read(10_000).decode("utf-8", "replace")
            if e.code == 400 and "is not registered" in body:
                raise NotRegistered("not registered") from None
            raise SignalApiError(f"the Signal API answered HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise SignalApiError(f"could not reach the Signal API ({type(e).__name__})") from None

    def _json(self, path):
        try:
            return json.loads(self._get(path))
        except ValueError:
            raise SignalApiError("unreadable answer from the Signal API") from None

    def accounts(self):
        data = self._json("/v1/accounts")
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            raise SignalApiError("unexpected answer from the Signal API")
        return data

    def devices(self, number):
        data = self._json("/v1/devices/" + urllib.parse.quote(number, safe="+"))
        ok = isinstance(data, list) and all(
            isinstance(d, dict) and isinstance(d.get("id"), int) and isinstance(d.get("name"), str)
            and isinstance(d.get("creation_timestamp"), int) for d in data)
        if not ok:
            raise SignalApiError("unexpected answer from the Signal API")
        return data

    def qr_png(self, device_name):
        body = self._get("/v1/qrcodelink?" + urllib.parse.urlencode({"device_name": device_name}))
        if not body.startswith(PNG_SIGNATURE):
            raise SignalApiError("the Signal API did not return a QR code image")
        return body
