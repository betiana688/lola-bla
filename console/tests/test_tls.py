"""Offline tests for the self-signed certificate. They write only into a temporary folder."""

import re
import stat
import tempfile
import unittest
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.x509.oid import ExtendedKeyUsageOID

from lola_console import tls


class Certificate(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name) / "tls"
        self.info = tls.make_certificate(self.dir, names=["reachy-mini.local", "localhost"], ips=["192.168.1.50"])
        self.cert = x509.load_pem_x509_certificate((self.dir / "cert.pem").read_bytes())

    def tearDown(self):
        self.tmp.cleanup()

    def test_private_key_is_owner_only(self):
        self.assertEqual(stat.S_IMODE((self.dir / "key.pem").stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.dir.stat().st_mode), 0o700)

    def test_names_and_addresses(self):
        san = self.cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        self.assertIn("reachy-mini.local", san.get_values_for_type(x509.DNSName))
        ips = [str(i) for i in san.get_values_for_type(x509.IPAddress)]
        self.assertIn("192.168.1.50", ips)
        self.assertIn("127.0.0.1", ips)

    def test_not_a_ca_and_server_auth_only(self):
        basic = self.cert.extensions.get_extension_for_class(x509.BasicConstraints).value
        self.assertFalse(basic.ca)
        eku = self.cert.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
        self.assertEqual(list(eku), [ExtendedKeyUsageOID.SERVER_AUTH])

    def test_validity_one_year(self):
        self.assertEqual((self.cert.not_valid_after_utc - self.cert.not_valid_before_utc).days, 365)

    def test_fingerprint_format(self):
        self.assertRegex(self.info["fingerprint"], r"^([0-9A-F]{2}:){31}[0-9A-F]{2}$")
        self.assertEqual(self.info["fingerprint"], tls.fingerprint(self.dir / "cert.pem"))

    def test_key_matches_certificate(self):
        key = serialization.load_pem_private_key((self.dir / "key.pem").read_bytes(), password=None)
        self.assertEqual(key.public_key().public_numbers(), self.cert.public_key().public_numbers())

    def test_regenerating_keeps_permissions(self):
        tls.make_certificate(self.dir, names=["reachy-mini.local"], ips=[])
        self.assertEqual(stat.S_IMODE((self.dir / "key.pem").stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
