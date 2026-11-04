"""A small client for the local signal-cli-rest-api. Standard library only.
Error messages never contain a phone number or a link code. The client has no way to delete
the Signal account itself: unregister always sends delete_account=false."""

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


def _number_path(number):
    return urllib.parse.quote(number, safe="+")


class SignalApi:
    def __init__(self, base_url=None, timeout=TIMEOUT_S, readonly=None):
        self.base = (base_url or os.environ.get("LOLA_SIGNAL_API", DEFAULT_URL)).rstrip("/")
        self.timeout = timeout
        # Read-only mode (LOLA_SIGNAL_READONLY=1) refuses everything except reading, so a test
        # console can look at the real Signal API without being able to change it.
        self.readonly = (os.environ.get("LOLA_SIGNAL_READONLY") == "1") if readonly is None else readonly

    def _deny_write(self):
        if self.readonly:
            raise SignalApiError("this console is in read-only mode")

    def _call(self, method, path, payload=None):
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                return resp.read(MAX_BYTES)
        except urllib.error.HTTPError as e:
            text = e.read(10_000).decode("utf-8", "replace")
            if e.code == 400 and "is not registered" in text:
                raise NotRegistered("not registered") from None
            raise SignalApiError(f"the Signal API answered HTTP {e.code}") from None
        except (urllib.error.URLError, OSError) as e:
            raise SignalApiError(f"could not reach the Signal API ({type(e).__name__})") from None

    def _json(self, path):
        try:
            return json.loads(self._call("GET", path))
        except ValueError:
            raise SignalApiError("unreadable answer from the Signal API") from None

    def accounts(self):
        data = self._json("/v1/accounts")
        if not isinstance(data, list) or not all(isinstance(x, str) for x in data):
            raise SignalApiError("unexpected answer from the Signal API")
        return data

    def devices(self, number):
        data = self._json("/v1/devices/" + _number_path(number))
        ok = isinstance(data, list) and all(
            isinstance(d, dict) and isinstance(d.get("id"), int) and isinstance(d.get("name"), str)
            and isinstance(d.get("creation_timestamp"), int) for d in data)
        if not ok:
            raise SignalApiError("unexpected answer from the Signal API")
        return data

    def groups(self, number):
        """The groups this account is in, reduced to what the console needs: internal_id, name,
        member_count and blocked. Member IDs are never passed on."""
        data = self._json("/v1/groups/" + _number_path(number))
        ok = isinstance(data, list) and all(
            isinstance(g, dict) and isinstance(g.get("internal_id"), str) and isinstance(g.get("name"), str)
            and isinstance(g.get("members", []), list) for g in data)
        if not ok:
            raise SignalApiError("unexpected answer from the Signal API")
        return [{"internal_id": g["internal_id"], "name": g["name"], "member_count": len(g.get("members", [])),
                 "blocked": bool(g.get("blocked", False))} for g in data]

    def qr_png(self, device_name):
        self._deny_write()
        body = self._call("GET", "/v1/qrcodelink?" + urllib.parse.urlencode({"device_name": device_name}))
        if not body.startswith(PNG_SIGNATURE):
            raise SignalApiError("the Signal API did not return a QR code image")
        return body

    def unregister(self, number):
        """Stop this app using the account. delete_account is always false: there is no way to ask
        this client to delete the Signal account itself."""
        self._deny_write()
        self._call("POST", "/v1/unregister/" + _number_path(number),
                   {"delete_account": False, "delete_local_data": False})

    def delete_local_data(self, number):
        """Delete this app's local Signal data. ignore_registered is always false, so the API
        refuses while the number is still registered."""
        self._deny_write()
        self._call("DELETE", "/v1/devices/" + _number_path(number) + "/local-data", {"ignore_registered": False})
