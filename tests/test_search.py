"""One runnable check that the DuckDuckGo result parser still works."""

import unittest

from term_helper import search

HTML = """
<a rel="nofollow" class="result__a" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fa&rut=x">Example <b>A</b></a>
<a class="result__snippet" href="https://example.com/a">First snippet.</a>
<a rel="nofollow" class="result__a" href="https://b.example/">Second</a>
<a class="result__snippet" href="https://b.example/">Second snippet.</a>
"""


class SearchParseTest(unittest.TestCase):
    def test_parse(self):
        rows = search.parse_ddg(HTML, 5)
        self.assertEqual(len(rows), 2)
        self.assertIn("https://example.com/a", rows[0])
        self.assertIn("Example A", rows[0])
        self.assertIn("First snippet.", rows[0])
        self.assertIn("https://b.example/", rows[1])

    def test_limit(self):
        self.assertEqual(len(search.parse_ddg(HTML, 1)), 1)


if __name__ == "__main__":
    unittest.main()
