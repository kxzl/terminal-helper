# terminal_helper

A keypress-driven, strictly local terminal assistant. It turns a question typed
at the prompt into either an answer or an approved sequence of shell actions.

## Language

**Core**:
The shell-agnostic Python program (`term-helper`) that assembles context, talks
to the local model, and enforces the allowlist.
_Avoid_: engine, backend, daemon

**Shim**:
The small per-shell snippet (fish/zsh/bash) that captures the current command
line, invokes the Core, and writes an inserted command back into the buffer.
_Avoid_: plugin, hook, adapter

**Ask**:
A single invocation of the helper, triggered by a keybinding, from prompt to
result.
_Avoid_: request, query, session

**Buffer**:
The command line the user is currently editing, captured by the Shim and sent
to the Core as context.
_Avoid_: input, line

**Plan**:
A model response describing one or more Steps to carry out.
_Avoid_: script, proposal

**Step**:
One shell command inside a Plan, with a rationale and a risk hint.
_Avoid_: action item, task

**Action**:
An executed Step, recorded in the audit log.
_Avoid_: operation

**Classification**:
The Core's advisory label for a Step — read-only or state-changing. It informs
the Approval prompt and gates nothing.
_Avoid_: allowlist, whitelist, permissions

**Approval**:
The `y/N` confirmation the user gives before a Step executes. Only `y` runs it.
_Avoid_: confirmation, consent

**History**:
The shell's command history, which the Shim appends executed Steps to so they
are reachable with `Ctrl+R`.
_Avoid_: log, audit log

**Suggest mode**:
The default role and keybinding, backed by the small fast model.
_Avoid_: normal mode, default

**Deep mode**:
The escalated keybinding (`Alt-:`), which asks the same model with a larger
token budget.
_Avoid_: think mode, pro

**Redaction**:
The removal of secret-shaped content from context before it reaches the model.
_Avoid_: sanitisation, masking

**Audit log**:
The append-only JSONL record of every Ask, Plan, decision, and Action.
_Avoid_: history, journal
