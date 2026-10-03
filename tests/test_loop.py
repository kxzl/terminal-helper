"""File reads run automatically; commands still need approval."""

import tempfile
import unittest
from pathlib import Path

from term_helper import loop


class Cfg:
    def get(self, key, default=None):
        return default


class ReadsTest(unittest.TestCase):
    def test_reads_are_automatic(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "note.txt"
            path.write_text("hello from a file")
            out = loop._handle_reads({"reads": [str(path)]}, Cfg())
            self.assertIn(f"read {path}", out)
            self.assertIn("hello from a file", out)

    def test_dry_run_does_not_read(self):
        out = loop._handle_reads({"reads": ["/nonexistent"]}, Cfg(), dry_run=True)
        self.assertIn("dry run", out)
        self.assertNotIn("could not read", out)


if __name__ == "__main__":
    unittest.main()
