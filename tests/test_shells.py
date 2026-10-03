"""Regression: every shim must bind Ctrl-G and Ctrl-Y, not just Alt-; / Alt-:."""

import unittest

from term_helper import shells


class ShimBindingTest(unittest.TestCase):
    def test_control_keys_bound_in_every_shim(self):
        expected = {"fish": (r"\cg", r"\cy"), "zsh": ("^G", "^Y"), "bash": (r"\C-g", r"\C-y")}
        for shell, (ask, deep) in expected.items():
            text = shells.shim_text(shell)
            self.assertIn(ask, text, f"{shell}: Ctrl-G not bound")
            self.assertIn(deep, text, f"{shell}: Ctrl-Y not bound")

    def test_fish_blank_line_before_repaint(self):
        # fish's repaint erases the line above it; without a blank line it wipes
        # the answer. The newline must come before commandline -f repaint.
        text = shells.shim_text("fish")
        self.assertIn("printf '\\n' >&2\n    commandline -f repaint", text)


if __name__ == "__main__":
    unittest.main()
