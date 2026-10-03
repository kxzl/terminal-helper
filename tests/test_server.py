"""Security boundary: llama-server may only bind loopback and not enable tools."""

import unittest
from types import SimpleNamespace

from term_helper import server


def role(url: str, extra=None):
    return SimpleNamespace(name="suggest", base_url=url, port=8080, extra_args=extra or [])


class ServerSecurityTest(unittest.TestCase):
    def test_loopback_ok(self):
        for url in ("http://127.0.0.1:8080", "http://localhost:8080", "http://[::1]:8080"):
            host, port = server._split_base(role(url))
            self.assertIn(host, {"127.0.0.1", "localhost", "::1"})
            self.assertEqual(port, 8080)

    def test_non_loopback_refused(self):
        for url in ("http://0.0.0.0:8080", "http://192.168.1.5:8080", "http://example.com"):
            with self.assertRaises(ValueError, msg=url):
                server._split_base(role(url))

    def test_forbidden_extra_args(self):
        with self.assertRaises(ValueError):
            server._extra_args(role("http://127.0.0.1:8080", ["--agent"]))
        self.assertEqual(
            server._extra_args(role("http://127.0.0.1:8080", ["-ngl", "99"])),
            ["-ngl", "99"],
        )


if __name__ == "__main__":
    unittest.main()
