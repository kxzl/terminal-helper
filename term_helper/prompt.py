"""A minimal line editor for the question prompt, with inline suggestions.

Suggestions come from past questions (the audit log) and a small vocabulary of
common shell words. Tab or Right-arrow accepts; the ghost text is dim.
"""

from __future__ import annotations

import os
import select
import termios

VOCAB = [
    "file", "files", "directory", "current", "find", "search", "grep", "list",
    "show", "how", "what", "where", "why", "which", "largest", "smallest", "size",
    "disk", "usage", "space", "free", "memory", "cpu", "process", "port", "service",
    "systemctl", "journal", "log", "logs", "git", "commit", "branch", "status",
    "diff", "stash", "remote", "push", "pull", "merge", "rebase", "docker",
    "container", "image", "volume", "network", "address", "dns", "ping", "curl",
    "download", "upload", "ssh", "key", "certificate", "permission", "chmod",
    "owner", "group", "date", "time", "sort", "count", "lines", "words", "hidden",
    "recursive", "recursively", "backup", "delete", "remove", "copy", "move",
    "rename", "compress", "extract", "archive", "tar", "zip", "install", "update",
    "upgrade", "package", "python", "version", "environment", "variable", "path",
    "changed", "modified", "recent", "yesterday", "today", "bigger", "smaller",
    "older", "newer", "empty", "duplicate", "compare", "count", "total", "top",
]


def _past_questions(limit: int = 200) -> list[str]:
    from term_helper import audit

    out = []
    for entry in reversed(audit.tail(limit)):
        if entry.get("event") == "ask" and entry.get("request"):
            out.append(str(entry["request"]))
    return out


def _words(texts) -> list[str]:
    seen: dict[str, str] = {}
    for text in texts:
        for word in text.split():
            word = word.strip(".,;:!?()[]{}\"'`")
            if 2 <= len(word) <= 24:
                seen.setdefault(word.lower(), word)
    return list(seen.values())


class LineEditor:
    def __init__(self, tty) -> None:
        self.tty = tty
        self.fd = tty._in.fileno()
        self.out = tty._out
        self.lines = _past_questions()
        self.words = sorted(set(VOCAB) | set(_words(self.lines)), key=str.lower)

    def suggest(self, line: str) -> str:
        if not line:
            return ""
        low = line.lower()
        for question in self.lines:
            if question.lower().startswith(low) and len(question) > len(line):
                return question[len(line):]
        word = line[line.rfind(" ") + 1:]
        if len(word) >= 2:
            low_word = word.lower()
            for candidate in self.words:
                if candidate.lower().startswith(low_word) and len(candidate) > len(word):
                    return candidate[len(word):]
        return ""

    def read(self, prompt: str) -> str | None:
        if not os.isatty(self.fd):
            return self.tty.prompt(prompt)

        saved = termios.tcgetattr(self.fd)
        raw = termios.tcgetattr(self.fd)
        raw[0] &= ~(termios.ICRNL | termios.IXON)
        raw[3] &= ~(termios.ICANON | termios.ECHO)
        raw[6][termios.VMIN] = 1
        raw[6][termios.VTIME] = 0

        line = ""
        try:
            termios.tcsetattr(self.fd, termios.TCSANOW, raw)
            self._render(prompt, line)
            while True:
                first = os.read(self.fd, 1)
                if not first:
                    break
                if first in (b"\r", b"\n"):
                    break
                if first == b"\x03":
                    line = None
                    break
                if first in (b"\x7f", b"\x08"):
                    line = line[:-1]
                elif first == b"\t":
                    line += self.suggest(line)
                elif first == b"\x1b":
                    seq = self._escape()
                    if seq.endswith("C"):        # Right arrow
                        line += self.suggest(line)
                elif first == b"\x15":
                    line = ""
                elif first[0] >= 32:
                    line += self._char(first)
                self._render(prompt, line)
            self.out.write("\r\n")
            self.out.flush()
            return line
        except KeyboardInterrupt:
            return None
        finally:
            termios.tcsetattr(self.fd, termios.TCSANOW, saved)

    def _escape(self) -> str:
        seq = ""
        while select.select([self.fd], [], [], 0.02)[0]:
            seq += os.read(self.fd, 1).decode("latin1")
        return seq

    def _char(self, first: bytes) -> str:
        data = bytearray(first)
        if first[0] >= 0xC0:
            need = 3 if first[0] >= 0xF0 else (2 if first[0] >= 0xE0 else 1)
            for _ in range(need):
                more = os.read(self.fd, 1)
                if not more:
                    break
                data += more
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return ""

    def _render(self, prompt: str, line: str) -> None:
        ghost = self.suggest(line) if line else ""
        self.out.write("\r\x1b[K" + prompt + line)
        if ghost:
            self.out.write("\x1b[2m" + ghost + "\x1b[0m")
        self.out.write(f"\r\x1b[{len(prompt) + len(line)}C")
        self.out.flush()
