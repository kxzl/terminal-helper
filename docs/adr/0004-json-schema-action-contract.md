# JSON-schema-constrained action contract

The model must answer with a single JSON object (`mode`, `answer`, `steps`) and
the server constrains decoding to that schema. Free-form prose was unusable for
planning, and native tool-calling is unreliable on the small local models this
tool targets. A hand-written GBNF grammar is the fallback for server versions
without `response_format`. Consequence: prompts are written to fill a schema
rather than to converse, and `mode` is ordered first so the Core can
short-circuit answers.
