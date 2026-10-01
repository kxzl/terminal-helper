"""A single dim, in-place status line on stderr (see Q24)."""

from __future__ import annotations

import re
import shutil
import sys

_STRING = re.compile(r'"(answer|cmd)"\s*:\s*"((?:[^"\\]|\\.)*)')
_ESCAPES = {"n": " ", "t": " ", '"': '"', "\\": "\\", "/": "/"}


def _unescape(text: str) -> str:
    return re.sub(r"\\(.)", lambda m: _ESCAPES.get(m.group(1), m.group(1)), text)


def preview(raw: str) -> str:
    """A readable slice of a partially-streamed JSON reply."""
    match = _STRING.search(raw)
    if not match:
        return "…"
    field, text = match.group(1), _unescape(match.group(2))
    return text if field == "answer" else "$ " + text


class Status:
    def __init__(self, stream=None, enabled: bool | None = None, prefix: str = "thinking… "):
        self.stream = stream or sys.stderr
        self.prefix = prefix
        self.enabled = self.stream.isatty() if enabled is None else enabled
        self._width = 0

    def update(self, text: str) -> None:
        if not self.enabled:
            return
        width = shutil.get_terminal_size((80, 24)).columns
        line = (self.prefix + text.replace("\n", " ")).strip()
        limit = max(10, width - 2)
        if len(line) > limit:
            line = "…" + line[-(limit - 1):]
        pad = " " * max(0, self._width - len(line))
        self.stream.write("\r\033[2m" + line + "\033[0m" + pad)
        self.stream.flush()
        self._width = len(line)

    def clear(self) -> None:
        if not self.enabled:
            return
        self.stream.write("\r" + " " * self._width + "\r")
        self.stream.flush()
        self._width = 0

    def __enter__(self) -> "Status":
        return self

    def __exit__(self, *exc) -> None:
        self.clear()


def note(message: str) -> None:
    print(f"\033[2m{message}\033[0m", file=sys.stderr)


def warn(message: str) -> None:
    print(f"\033[33m{message}\033[0m", file=sys.stderr)


def error(message: str) -> None:
    print(f"\033[31m{message}\033[0m", file=sys.stderr)
