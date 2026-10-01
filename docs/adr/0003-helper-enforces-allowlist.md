# The Core enforces the allowlist, never the model

Status: superseded by [ADR-0007](0007-every-command-requires-approval.md).

The model returns a `risk` field per Step, but the Core treats it as a hint and
independently classifies every command against the allowlist. A local model's
self-assessment is not a security boundary. Considered: trusting the model's
risk label (simpler, unsafe) and native tool-calling with model-declared safety
(unsafe and unreliable on small local models). Consequence: the allowlist in
`term_helper/policy.py` is the single place to change what runs unattended.
