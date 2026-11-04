"""Passwords for the Lola-Bla console: hashing, checking, and the rules.
Standard library only. Nothing here ever prints or logs a password."""

import base64
import hashlib
import hmac
import re
import secrets

# scrypt cost. The values are stored inside every hash, so they can be raised later
# without breaking existing passwords.
SCRYPT_N = 2 ** 15
SCRYPT_R = 8
SCRYPT_P = 1
SALT_BYTES = 16
KEY_BYTES = 32
MAXMEM = 128 * 1024 * 1024  # N=2**15, r=8 needs about 32 MiB; leave headroom

MIN_PASSWORD_LENGTH = 12
MAX_PASSWORD_LENGTH = 128
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
# A tiny list of easy guesses. Deliberately not a full dictionary.
EASY_PARTS = ("password", "passwort", "contrasena", "contraseña", "123456", "qwerty", "lolabla", "reachy")


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P,
                         maxmem=MAXMEM, dklen=KEY_BYTES)
    return "$".join(["scrypt", str(SCRYPT_N), str(SCRYPT_R), str(SCRYPT_P),
                     base64.b64encode(salt).decode("ascii"), base64.b64encode(key).decode("ascii")])


def verify_password(password: str, stored: str) -> bool:
    """True only if `password` matches `stored`. Any malformed hash counts as a mismatch."""
    try:
        scheme, n, r, p, salt_b64, key_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64.encode("ascii"), validate=True)
        expected = base64.b64decode(key_b64.encode("ascii"), validate=True)
        key = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p),
                             maxmem=MAXMEM, dklen=len(expected))
    except Exception:
        return False
    return hmac.compare_digest(key, expected)


def check_username(username: str) -> list:
    if USERNAME_RE.match(username or ""):
        return []
    return ["username must be 3 to 32 characters: a-z, 0-9, dot, dash or underscore, "
            "starting with a letter or digit"]


def check_password(password: str, username: str = "") -> list:
    """Problems with a proposed password, in plain words. An empty list means it is fine."""
    problems = []
    try:
        password.encode("utf-8")
    except UnicodeEncodeError:
        return ["contains characters that cannot be stored"]
    if len(password) < MIN_PASSWORD_LENGTH:
        problems.append(f"too short (at least {MIN_PASSWORD_LENGTH} characters)")
    if len(password) > MAX_PASSWORD_LENGTH:
        problems.append(f"too long (at most {MAX_PASSWORD_LENGTH} characters)")
    lowered = password.lower()
    if password and len(set(password)) <= 2:
        problems.append("too repetitive")
    if username and len(username) >= 4 and username.lower() in lowered:
        problems.append("must not contain the username")
    if any(part in lowered for part in EASY_PARTS):
        problems.append("contains something easy to guess (like 'password' or 'qwerty')")
    return problems
