"""Context assembly and redaction (see docs/adr/0001 and Q8/Q18 decisions)."""

from __future__ import annotations

import os
import platform
import re
import subprocess
from pathlib import Path

SECRET = re.compile(
    r"(?i)\b(token|secret|password|passwd|api[_-]?key|apikey|bearer|authorization|"
    r"credential|client[_-]?secret)\b(\s*[=:]\s*)\S+"
)
SECRET_FLAG = re.compile(r"(?i)(--password|--token|--secret|--api-key|--apikey)(=|\s+)\S+")
URL_CRED = re.compile(r"(https?://)[^/\s:@]+:[^/\s@]+@")


def redact(text: str) -> str:
    text = SECRET.sub(r"\1\2***", text)
    text = SECRET_FLAG.sub(r"\1\2***", text)
    text = URL_CRED.sub(r"\1***@", text)
    return text


def _truncate(line: str, limit: int) -> str:
    line = line.strip()
    return line if len(line) <= limit else line[: limit - 1] + "…"


def _read_lines(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def _fish_history() -> list[str]:
    for candidate in (
        Path.home() / ".local" / "share" / "fish" / "fish_history",
        Path.home() / ".config" / "fish" / "fish_history",
    ):
        lines = _read_lines(candidate)
        if lines:
            return [ln.split("cmd:", 1)[1].strip() for ln in lines if "cmd:" in ln]
    return []


def _zsh_history() -> list[str]:
    histfile = os.environ.get("HISTFILE") or str(Path.home() / ".zsh_history")
    out: list[str] = []
    for line in _read_lines(Path(histfile)):
        if line.startswith(": ") and ";" in line:
            line = line.split(";", 1)[1]
        out.append(line)
    return out


def _bash_history() -> list[str]:
    histfile = os.environ.get("HISTFILE") or str(Path.home() / ".bash_history")
    return _read_lines(Path(histfile))


def recent_commands(shell: str, lines: int, max_chars: int) -> list[str]:
    readers = {"fish": _fish_history, "zsh": _zsh_history, "bash": _bash_history}
    reader = readers.get(shell)
    if reader is None:
        return []
    history = [ln for ln in reader() if ln.strip()]
    recent = history[-lines:]
    return [redact(_truncate(ln, max_chars)) for ln in recent]


def git_summary(cwd: str, limit: int = 20) -> str:
    try:
        inside = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=cwd, capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return ""
    try:
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "-b"],
            cwd=cwd, capture_output=True, text=True, timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    out = [redact(ln) for ln in status.stdout.splitlines()[:limit]]
    return "\n".join(out)


def dir_listing(cwd: str, limit: int = 40) -> str:
    try:
        entries = sorted(os.listdir(cwd))
    except OSError:
        return ""
    rendered = []
    for name in entries[:limit]:
        full = os.path.join(cwd, name)
        rendered.append(name + "/" if os.path.isdir(full) else name)
    if len(entries) > limit:
        rendered.append(f"… (+{len(entries) - limit} more)")
    return "  ".join(rendered)


def build_messages(cfg, *, shell: str, cwd: str, buffer: str, request: str,
                   extra: str = "") -> list[dict]:
    from term_helper.contract import system_prompt

    history = recent_commands(shell, int(cfg.get("history_lines", 15)),
                              int(cfg.get("history_max_chars", 200)))
    lines = [
        "[context]",
        f"cwd: {cwd}",
        f"shell: {shell or 'unknown'}",
        f"os: {platform.system()} {platform.release()}",
    ]
    model = cfg.role("suggest").model
    if model:
        lines.append(f"model: {model}")
    if buffer.strip():
        lines.append(f"current command line: {redact(buffer)}")
    git = git_summary(cwd)
    if git:
        lines.append("git status:")
        lines.extend("  " + ln for ln in git.splitlines())
    listing = dir_listing(cwd)
    if listing:
        lines.append(f"files: {listing}")
    if history:
        lines.append("recent commands (oldest first):")
        lines.extend(f"  {i + 1}. {ln}" for i, ln in enumerate(history))
    lines.append("[/context]")
    if extra:
        lines.append("")
        lines.append(extra)
    lines.append("")
    lines.append(f"request: {redact(request)}")
    return [
        {"role": "system", "content": system_prompt(shell, bool(cfg.get("web_search", False)))},
        {"role": "user", "content": "\n".join(lines)},
    ]


def read_file(path: str, max_lines: int, max_bytes: int) -> str:
    target = Path(os.path.expanduser(path))
    try:
        raw = target.read_bytes()[:max_bytes]
    except OSError as exc:
        return f"<could not read {path}: {exc}>"
    text = raw.decode("utf-8", errors="replace")
    lines = text.splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines] + [f"… truncated after {max_lines} lines"]
    return redact("\n".join(lines))
