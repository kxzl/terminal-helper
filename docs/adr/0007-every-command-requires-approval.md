# Every command requires approval; no auto-run

Nothing the model proposes executes unattended. Each Step is printed with its
rationale and confirmed with `y/N`, and only `y` runs it. We originally
auto-ran a read-only allowlist and gated everything else; in practice the user
wants to see the exact command before it touches their machine, and read-only
commands were not the ones that needed review anyway. Considered: keeping the
allowlist with a "trust read-only" switch (rejected — the classification is a
heuristic over shell text, not a guarantee). Consequence: `policy.py` is now
advisory only, the model's `risk` field is a hint, and every command costs one
keystroke. Supersedes ADR-0003.
