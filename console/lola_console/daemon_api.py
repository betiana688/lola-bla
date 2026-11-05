"""The robot service (Reachy Mini daemon) as the console sees it. Only the robot itself, only two calls.
The address is fixed on purpose: the console never talks to anything else, and no setting can change that."""

import json
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
APP_NAME = "lola_bla"  # the name Lola-Bla will have as an installed Reachy Mini app


class DaemonError(RuntimeError):
    """The robot service could not be reached or gave an answer we do not understand.
    `status` is the HTTP status when the service answered with an error, else None."""

    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


class DaemonClient:
    def __init__(self, base=BASE, timeout=3):  # `base` is only for the tests
        self.base = base
        self.timeout = timeout

    def _call(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"} if data is not None else {}
        request = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode())
        except urllib.error.HTTPError as e:
            raise DaemonError(f"the robot service answered {e.code}", status=e.code)
        except (urllib.error.URLError, OSError, ValueError) as e:
            raise DaemonError(f"robot service: {type(e).__name__}")

    def installed_names(self):
        answer = self._call("GET", "/api/apps/list-available/installed")
        if not isinstance(answer, list) or not all(isinstance(a, dict) and isinstance(a.get("name"), str) for a in answer):
            raise DaemonError("unexpected answer to the installed apps list")
        return [a["name"] for a in answer]

    def startup_app(self):
        answer = self._call("GET", "/api/apps/startup-app")
        value = answer.get("startup_app") if isinstance(answer, dict) else None
        if not isinstance(answer, dict) or "startup_app" not in answer or not (value is None or isinstance(value, str)):
            raise DaemonError("unexpected answer to the startup setting")
        return value

    def set_startup_app(self, name):
        """Set the app that starts at wake-up, or clear it with None. The service only accepts installed apps."""
        self._call("PUT", "/api/apps/startup-app", {"startup_app": name})
