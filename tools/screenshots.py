#!/usr/bin/env python3
"""Render README screenshots from the real ANSI the tool emits.

Run from the repo root:  python3 tools/screenshots.py

It drives the actual render/loop/prompt code with fixed input, feeds the ANSI
through a minimal terminal emulator, and paints the result with Pillow. The
pictures show what the tool really prints; only the model's reply is canned and
the setup screenshot anonymizes the username and hardware.
"""

from __future__ import annotations

import io
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

FONT_CANDIDATES = [
    ("/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
     "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"),
    ("/usr/share/fonts/adwaita-mono-fonts/AdwaitaMono-Regular.ttf",
     "/usr/share/fonts/adwaita-mono-fonts/AdwaitaMono-Bold.ttf"),
    ("/usr/share/fonts/google-noto-vf/NotoSansMono[wght].ttf",
     "/usr/share/fonts/google-noto-vf/NotoSansMono[wght].ttf"),
    ("/usr/share/fonts/liberation-mono-fonts/LiberationMono-Regular.ttf",
     "/usr/share/fonts/liberation-mono-fonts/LiberationMono-Bold.ttf"),
]
SIZE = 17
PAD = 22
TITLEBAR = 40
BG = (30, 34, 42)
BAR = (43, 48, 59)
FG = (216, 222, 233)
DIM = (124, 134, 148)
COLORS = {31: (248, 113, 113), 32: (163, 230, 53), 33: (251, 191, 36),
          36: (103, 232, 249), 37: FG}
OUT = Path(__file__).resolve().parent.parent / "docs" / "screenshots"


@dataclass
class Cell:
    ch: str = " "
    fg: tuple = FG
    dim: bool = False
    bold: bool = False


@dataclass
class Screen:
    cols: int = 110
    rows: list[list[Cell]] = field(default_factory=lambda: [[]])
    x: int = 0

    def _line(self) -> list[Cell]:
        return self.rows[-1]

    def feed(self, text: str, style: tuple) -> None:
        i = 0
        while i < len(text):
            ch = text[i]
            if ch == "\x1b" and i + 1 < len(text) and text[i + 1] == "[":
                j = i + 2
                while j < len(text) and not text[j].isalpha():
                    j += 1
                self._csi(text[i + 2:j], text[j] if j < len(text) else "")
                i = j + 1
                continue
            if ch == "\n":
                self.rows.append([])
                self.x = 0
            elif ch == "\r":
                self.x = 0
            elif ch == "\b":
                self.x = max(0, self.x - 1)
            else:
                line = self._line()
                while len(line) < self.x:
                    line.append(Cell())
                cell = Cell(ch, style[0], style[1], style[2])
                if self.x < len(line):
                    line[self.x] = cell
                else:
                    line.append(cell)
                self.x += 1
            i += 1

    def _csi(self, params: str, final: str) -> None:
        try:
            n = int(params) if params.isdigit() else 1
        except ValueError:
            n = 1
        if final == "K":
            line = self._line()
            del line[self.x:]
        elif final == "C":
            self.x += n
        elif final == "D":
            self.x = max(0, self.x - n)
        elif final == "A":
            self.x = 0


def render(screen: Screen, path: Path) -> None:
    font = bold = ImageFont.load_default()
    for regular, bold_path in FONT_CANDIDATES:
        if Path(regular).exists() and Path(bold_path).exists():
            font = ImageFont.truetype(regular, SIZE)
            bold = ImageFont.truetype(bold_path, SIZE)
            break
    adv = font.getlength("M")
    height = font.getbbox("Ag")[3] + 7
    lines = screen.rows
    while lines and not any(c.ch.strip() for c in lines[-1]):
        lines.pop()
    while lines and not any(c.ch.strip() for c in lines[0]):
        lines.pop(0)

    width = int(PAD * 2 + max(len(line) for line in lines) * adv) + 2
    height_px = int(TITLEBAR + PAD * 2 + len(lines) * height)
    img = Image.new("RGB", (width, height_px), BG)
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 0, width, TITLEBAR], fill=BAR)
    for i, color in enumerate([(237, 106, 94), (245, 191, 79), (98, 197, 84)]):
        cx = 20 + i * 20
        draw.ellipse([cx - 6, TITLEBAR // 2 - 6, cx + 6, TITLEBAR // 2 + 6], fill=color)

    y = TITLEBAR + PAD
    for line in lines:
        x = PAD
        for cell in line:
            if cell.ch != " ":
                fg = DIM if cell.dim else cell.fg
                draw.text((x, y), cell.ch, font=bold if cell.bold else font, fill=fg)
            x += adv
        y += height
    img.save(path)
    print(f"wrote {path} ({width}x{height_px})")


def ansi_screen(text: str) -> Screen:
    screen = Screen()
    fg, dim, bold = FG, False, False
    i = 0
    while i < len(text):
        if text.startswith("\x1b[", i):
            j = i + 2
            while j < len(text) and not text[j].isalpha():
                j += 1
            codes = text[i + 2:j].split(";") if text[i + 2:j] else ["0"]
            if text[j] == "m":
                for code in codes:
                    c = code or "0"
                    if c == "0":
                        fg, dim, bold = FG, False, False
                    elif c == "2":
                        dim = True
                    elif c == "1":
                        bold = True
                    elif c.isdigit() and int(c) in COLORS:
                        fg = COLORS[int(c)]
            else:
                screen._csi(text[i + 2:j], text[j])
            i = j + 1
            continue
        screen.feed(text[i], (fg, dim, bold))
        i += 1
    return screen


# ---------------------------------------------------------------- captures


def shot_suggest() -> str:
    from term_helper import prompt as prompt_mod

    class FakeTty:
        def __init__(self):
            self._in = os.fdopen(os.dup(0), "r")
            self._out = io.StringIO()

    tty = FakeTty()
    editor = prompt_mod.LineEditor(tty)
    editor.lines = ["how many letter p's are in all files in this folder"]
    editor.words = ["files", "folder", "letter"]
    editor._render("? ", "how many letter p")
    return tty._out.getvalue()


def shot_approve() -> str:
    import contextlib

    from term_helper import config, loop

    out = io.StringIO()

    class FakeTty:
        def __init__(self):
            self.inputs = ["y\n"]

        def write(self, text):
            out.write(text)

        def readline(self):
            line = self.inputs.pop(0) if self.inputs else ""
            out.write(line)          # a real terminal echoes what you type
            return line

        def prompt(self, text):
            self.write(text)
            return self.readline().strip()

        def close(self):
            pass

    real_tty, real_exec = loop.Tty, loop.execute
    loop.Tty = FakeTty
    loop.execute = lambda cmd, cwd, tty, shell="": (
        0, "1.4G\t./models\n 88M\t./llama.cpp\n 12M\t./docs\n")
    try:
        plan = {"mode": "plan", "steps": [{
            "cmd": "du -h --max-depth=1 | sort -hr | head -n 3",
            "why": "List directory sizes, biggest first.",
            "risk": "read", "reads": []}]}
        with contextlib.redirect_stderr(out):
            loop.run_plan(
                config.default_config(), [], plan, cwd=".", shell="fish",
                continue_fn=lambda msgs: {
                    "mode": "answer",
                    "answer": "The models directory is the biggest at 1.4G; "
                              "llama.cpp is 88M and docs 12M."},
            )
    finally:
        loop.Tty, loop.execute = real_tty, real_exec
    return out.getvalue()


def _anonymize(text: str) -> str:
    """Replace the local username and hardware specs in captured output."""
    text = text.replace(str(Path.home()), "/home/you")
    text = re.sub(r"(?m)^(\x1b\[2m  CPU\s+)[^\x1b\n]*", r"\g<1>8 cores", text)
    text = re.sub(r"(?m)^(\x1b\[2m  RAM\s+)[^\x1b\n]*", r"\g<1>32 GB", text)
    text = re.sub(r"(?m)^(\x1b\[2m  GPU\s+)[^\x1b\n]*", r"\g<1>AMD Radeon (8 GB VRAM)", text)
    return text


def shot_setup() -> str:
    import subprocess

    from term_helper import config

    # `setup` rewrites the config; put the user's copy back afterwards.
    backup = config.CONFIG_PATH.read_bytes() if config.CONFIG_PATH.exists() else None
    try:
        proc = subprocess.run([sys.executable, "-m", "term_helper", "setup"],
                              input="\n", capture_output=True, text=True,
                              env={**os.environ,
                                   "PYTHONPATH": str(Path(__file__).resolve().parent.parent)})
    finally:
        if backup is not None:
            config.CONFIG_PATH.write_bytes(backup)
    return _anonymize(proc.stderr)


def shot_modes() -> str:
    """The banner: one keypress, all three kinds of reply."""
    import contextlib

    from term_helper import config, loop, render

    out = io.StringIO()

    class FakeTty:
        def __init__(self):
            self.inputs = ["y\n"]

        def write(self, text):
            out.write(text)

        def readline(self):
            line = self.inputs.pop(0) if self.inputs else ""
            out.write(line)
            return line

        def prompt(self, text):
            self.write(text)
            return self.readline().strip()

        def close(self):
            pass

    real_tty, real_exec = loop.Tty, loop.execute
    loop.Tty = FakeTty
    loop.execute = lambda cmd, cwd, tty, shell="": (
        0, 'LISTEN 0 4096 127.0.0.1:8080 0.0.0.0:* '
           'users:(("llama-server",pid=4242,fd=9))\n')
    try:
        out.write("? what's using port 8080?\n")
        plan = {"mode": "plan", "steps": [{
            "cmd": "ss -ltnp 'sport = :8080'",
            "why": "show the process listening on port 8080",
            "risk": "read", "reads": []}]}
        with contextlib.redirect_stderr(out):
            loop.run_plan(config.default_config(), [], plan, cwd=".", shell="bash",
                          continue_fn=None)
    finally:
        loop.Tty, loop.execute = real_tty, real_exec

    out.write("\n? what's the difference between a hardlink and a symlink?\n\n")
    out.write("  A hardlink is another name for the same inode, so the two names are\n")
    out.write("  truly equal; a symlink is a separate file that points at a path.\n")

    out.write("\n? what's the latest stable linux kernel version?\n\n")
    with contextlib.redirect_stderr(out):
        render.note("↗ web search (DuckDuckGo): latest stable linux kernel version")
    out.write("  The latest stable release is ...\n")
    return out.getvalue()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    render(ansi_screen(shot_modes()), OUT / "modes.png")
    render(ansi_screen(shot_suggest()), OUT / "suggest.png")
    render(ansi_screen(shot_approve()), OUT / "approve.png")
    render(ansi_screen(shot_setup()), OUT / "setup.png")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
