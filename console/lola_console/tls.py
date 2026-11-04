"""Self-signed HTTPS certificate for the console, using the `cryptography` package.
The private key is created owner-only and never leaves the Pi."""

import datetime
import ipaddress
import os
import subprocess
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

TLS_DIR = Path.home() / ".config" / "lola-bla" / "tls"
VALID_DAYS = 365
DEFAULT_NAMES = ["reachy-mini.local", "reachy-mini", "localhost"]


def extra_names():
    """More host names the console answers to: LOLA_CONSOLE_HOSTS=name1,name2"""
    return [n.strip() for n in os.environ.get("LOLA_CONSOLE_HOSTS", "").split(",") if n.strip()]


def local_ips():
    """The Pi's own non-loopback IPv4 addresses, so the certificate also works by address."""
    found = []
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True, text=True, timeout=5).stdout
        for part in out.split():
            try:
                ip = ipaddress.ip_address(part)
            except ValueError:
                continue
            if ip.version == 4 and not ip.is_loopback:
                found.append(str(ip))
    except Exception:
        pass
    return found


def allowed_hosts():
    return DEFAULT_NAMES + extra_names() + ["127.0.0.1"] + local_ips()


def _fingerprint(cert) -> str:
    raw = cert.fingerprint(hashes.SHA256()).hex().upper()
    return ":".join(raw[i:i + 2] for i in range(0, len(raw), 2))


def fingerprint(cert_path) -> str:
    return _fingerprint(x509.load_pem_x509_certificate(Path(cert_path).read_bytes()))


def make_certificate(tls_dir=TLS_DIR, names=None, ips=None, days=VALID_DAYS) -> dict:
    tls_dir = Path(tls_dir)
    tls_dir.mkdir(parents=True, exist_ok=True)
    tls_dir.chmod(0o700)
    names = list(names) if names is not None else DEFAULT_NAMES + extra_names()
    ips = (list(ips) if ips is not None else local_ips()) + ["127.0.0.1"]

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Lola-Bla console")])
    now = datetime.datetime.now(datetime.timezone.utc)
    san = [x509.DNSName(n) for n in names] + [x509.IPAddress(ipaddress.ip_address(i)) for i in ips]
    cert = (x509.CertificateBuilder()
            .subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=5))
            .not_valid_after(now + datetime.timedelta(days=days))
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.KeyUsage(
                digital_signature=True, content_commitment=False, key_encipherment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False, crl_sign=False,
                encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .sign(key, hashes.SHA256()))

    key_path, cert_path = tls_dir / "key.pem", tls_dir / "cert.pem"
    key_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption())
    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(key_pem)
    os.chmod(key_path, 0o600)
    cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    os.chmod(cert_path, 0o644)
    return {
        "cert_path": str(cert_path), "key_path": str(key_path), "names": names + ips,
        "expires": (now + datetime.timedelta(days=days)).date().isoformat(),
        "fingerprint": _fingerprint(cert),
    }
