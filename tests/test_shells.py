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


if __name__ == "__main__":
    unittest.main()
