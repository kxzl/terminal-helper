"""Checks for the model output contract and its fence fallback."""

import unittest

from term_helper import contract


class ContractTest(unittest.TestCase):
    def test_answer(self):
        self.assertEqual(contract.parse('{"mode":"answer","answer":"hi"}')["mode"], "answer")

    def test_plan(self):
        raw = '{"mode":"plan","steps":[{"cmd":"ls","why":"","risk":"read"}]}'
        result = contract.parse(raw)
        self.assertEqual(result["steps"][0]["cmd"], "ls")

    def test_shell_fence_becomes_plan(self):
        raw = '{"mode":"answer","answer":"Use:\\n```sh\\nls -lhS | head -n 4\\n```"}'
        result = contract.parse(raw)
        self.assertEqual(result["mode"], "plan")
        self.assertEqual(result["steps"][0]["cmd"], "ls -lhS | head -n 4")

    def test_non_shell_fence_stays_answer(self):
        raw = '{"mode":"answer","answer":"like:\\n```python\\nprint(1)\\n```"}'
        self.assertEqual(contract.parse(raw)["mode"], "answer")

    def test_fenced_json_is_unwrapped(self):
        self.assertEqual(contract.parse('```json\n{"mode":"answer","answer":"x"}\n```')["mode"],
                         "answer")

    def test_empty_answer_raises(self):
        with self.assertRaises(contract.ContractError):
            contract.parse('{"mode":"answer","answer":""}')

    def test_plan_without_steps_raises(self):
        with self.assertRaises(contract.ContractError):
            contract.parse('{"mode":"plan","steps":[]}')

    def test_search(self):
        result = contract.parse('{"mode":"search","query":"arch linux news"}')
        self.assertEqual(result["mode"], "search")
        self.assertEqual(result["query"], "arch linux news")

    def test_search_without_query_raises(self):
        with self.assertRaises(contract.ContractError):
            contract.parse('{"mode":"search"}')


if __name__ == "__main__":
    unittest.main()
