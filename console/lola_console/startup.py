"""Start Lola-Bla when the robot wakes up: read and change the robot service's startup setting.
The setting always lives in the robot service; nothing is copied here. Turning off only ever clears
Lola-Bla's own entry, never another app's."""

from .daemon_api import APP_NAME, DaemonError


def _state(state, text, other=None):
    return {"state": state, "text": text, "other": other,
            "can_turn_on": state in ("off", "other"), "can_turn_off": state == "on"}


def get_state(client, app_name=APP_NAME):
    try:
        installed = client.installed_names()
        current = client.startup_app()
    except DaemonError:
        return _state("unavailable", "can't reach the robot service right now. nothing is changed.")
    if current == app_name:
        return _state("on", "on. lola-bla starts when the robot wakes up.")
    if app_name not in installed:
        return _state("not_installed", "lola-bla is not installed as a reachy mini app yet, so this can't be switched on.")
    if current is None:
        return _state("off", "off. lola-bla starts only when you start it yourself.")
    return _state("other", f"another app starts at wake-up: {current}. turning this on replaces it.", other=current)


def _result(changed, notice, audit=None, error=None):
    return {"changed": changed, "notice": notice, "audit": audit, "error": error}


def change(client, action, app_name=APP_NAME):
    """Turn the setting "on" or "off". Returns what happened; never raises."""
    if action not in ("on", "off"):
        return _result(False, "startup_nothing")
    state = get_state(client, app_name)["state"]
    if state == "unavailable":
        return _result(False, "startup_unreachable", error="could not reach the robot service")
    if action == "on":
        if state == "on":
            return _result(False, "startup_already_on")
        if state == "not_installed":
            return _result(False, "startup_not_installed")
        target = app_name
    else:
        if state != "on":
            return _result(False, "startup_already_off")
        target = None
    try:
        client.set_startup_app(target)
        now = client.startup_app()
    except DaemonError as e:
        if e.status is not None:
            return _result(False, "startup_failed", error="the robot service refused the startup setting")
        return _result(False, "startup_unreachable", error="could not reach the robot service")
    if now != target:
        return _result(False, "startup_failed", error="the robot service did not keep the startup setting")
    return _result(True, "startup_on" if action == "on" else "startup_off",
                   audit="startup_on" if action == "on" else "startup_off")
