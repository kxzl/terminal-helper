"""The model output contract: a JSON schema, a GBNF fallback, and a parser."""

from __future__ import annotations

import json
import re
from typing import Any

# Shell fences the model sometimes emits inside "answer" text.
FENCE = re.compile(r"```([a-zA-Z0-9_-]*)\n(.*?)```", re.S)
SHELL_LANGS = {"", "sh", "bash", "zsh", "fish", "shell", "console", "shell-session"}

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "mode": {"type": "string", "enum": ["answer", "plan"]},
        "answer": {"type": "string"},
        "steps": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "cmd": {"type": "string"},
                    "why": {"type": "string"},
                    "risk": {"type": "string", "enum": ["read", "write", "destructive"]},
                    "reads": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["cmd", "why", "risk"],
            },
        },
    },
    "required": ["mode"],
}

# Fallback for llama-server builds without response_format support.
GBNF = r"""
root   ::= object
object ::= "{" ws "\"mode\"" ws ":" ws mode ("," ws "\"answer\"" ws ":" ws string)? ("," ws "\"steps\"" ws ":" ws steps)? ws "}"
mode   ::= "\"answer\"" | "\"plan\""
steps  ::= "[" ws (step (ws "," ws step)*)? ws "]"
step   ::= "{" ws "\"cmd\"" ws ":" ws string ws "," ws "\"why\"" ws ":" ws string ws "," ws "\"risk\"" ws ":" ws risk ws "}"
risk   ::= "\"read\"" | "\"write\"" | "\"destructive\""
string ::= "\"" ([^"\\] | "\\" .)* "\""
ws     ::= [ \t\n]*
"""

SYSTEM_PROMPT = """\
You are a terminal helper running on the user's Linux machine. The user asks a
question from their shell prompt. Reply with ONE JSON object matching the
provided schema and nothing else.

Use mode="answer" ONLY for pure explanations that contain no commands at all.
Never put shell commands inside the "answer" text, and never use code fences
there.

Use mode="plan" whenever the user asks you to do, find, list, show, change,
install, delete, or run anything — even when a single command would do. Put the
commands in "steps". Each step is:
  cmd   - one shell command, ready to run verbatim. One command per step.
  why   - one short sentence explaining the step.
  risk  - "read" (no side effects), "write" (creates or modifies something), or
          "destructive" (deletes, overwrites, or is hard to undo).
  reads - optional list of file paths the step needs to read.

Rules:
- Prefer the fewest steps that finish the job.
- Never include "sudo" unless the user explicitly asked for it.
- Never pipe into a shell (for example "curl ... | sh") and never use command
  substitution.
- The user's shell is {shell}. Prefer portable commands.
- "risk" is only a hint; the user's tool classifies commands independently.
- If you are unsure what the user wants, answer with mode="answer" and ask.
"""


def system_prompt(shell: str) -> str:
    return SYSTEM_PROMPT.format(shell=shell or "unknown")


class ContractError(ValueError):
    pass


def _commands_in(answer: str) -> list[str]:
    """Extract runnable commands from shell fences in an answer, if any."""
    commands: list[str] = []
    for lang, body in FENCE.findall(answer):
        if lang.lower() not in SHELL_LANGS:
            continue
        for line in body.splitlines():
            line = line.strip()
            if line and not line.startswith("#"):
                commands.append(line)
    return commands


def parse(raw: str) -> dict[str, Any]:
    """Parse a model response into a validated result dict."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ContractError(f"model did not return JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ContractError("model returned JSON that is not an object")

    mode = data.get("mode")
    if mode not in ("answer", "plan"):
        # Be forgiving: infer from the shape rather than failing outright.
        mode = "plan" if data.get("steps") else "answer"
    data["mode"] = mode

    if mode == "answer":
        answer = str(data.get("answer") or "").strip()
        if not answer:
            raise ContractError("answer mode with an empty answer")
        commands = _commands_in(answer)
        if commands:
            # The model explained instead of planning. Honour the commands it
            # handed back so they still go through the approval loop.
            return {
                "mode": "plan",
                "steps": [
                    {"cmd": cmd, "why": "from the model's explanation",
                     "risk": "write", "reads": []}
                    for cmd in commands
                ],
            }
        return {"mode": "answer", "answer": answer}

    steps = data.get("steps") or []
    if not isinstance(steps, list):
        raise ContractError("steps must be a list")
    clean: list[dict[str, Any]] = []
    for step in steps:
        if not isinstance(step, dict):
            continue
        cmd = str(step.get("cmd") or "").strip()
        if not cmd:
            continue
        clean.append(
            {
                "cmd": cmd,
                "why": str(step.get("why") or "").strip(),
                "risk": str(step.get("risk") or "write").strip().lower(),
                "reads": [str(p) for p in step.get("reads") or [] if str(p).strip()],
            }
        )
    if not clean:
        raise ContractError("plan mode with no usable steps")
    return {"mode": "plan", "steps": clean}
