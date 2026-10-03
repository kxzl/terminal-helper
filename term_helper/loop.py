"""The execute -> observe -> confirm loop.

Every Step is shown and confirmed with y/N; nothing runs unattended. Commands
that ran are returned so the Shell Shim can record them in shell history.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

from term_helper import audit, policy, render

MAX_OUTPUT = 4000


class Tty:
    """Reads prompts from /dev/tty so piped stdin never breaks the loop.

    /dev/tty cannot be opened "r+" (it is not seekable), so read and write use
    separate handles. The invoking shell's line editor leaves the terminal in
    raw mode, so we restore canonical mode with echo while we own it.
    """

    def __init__(self) -> None:
        self._in = None
        self._out = None
        self._owns = False
        try:
            self._in = open("/dev/tty", "r")
            self._out = open("/dev/tty", "w")
            self._owns = True
        except OSError:
            self._in = sys.stdin
            self._out = sys.stderr
        self._saved = None
        try:
            import termios

            fd = self._in.fileno()
            self._saved = termios.tcgetattr(fd)
            attrs = termios.tcgetattr(fd)
            attrs[0] |= termios.ICRNL          # Enter sends CR; map it to NL
            attrs[3] |= termios.ICANON | termios.ECHO
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
        except Exception:  # noqa: BLE001 - best effort
            self._saved = None

    def write(self, text: str) -> None:
        self._out.write(text)
        self._out.flush()

    def readline(self) -> str:
        return self._in.readline()

    def prompt(self, text: str) -> str:
        self.write(text)
        return self.readline().strip()

    def close(self) -> None:
        if self._saved is not None:
            try:
                import termios

                termios.tcsetattr(self._in.fileno(), termios.TCSANOW, self._saved)
            except Exception:  # noqa: BLE001
                pass
        if self._owns:
            for handle in (self._in, self._out):
                try:
                    handle.close()
                except Exception:  # noqa: BLE001
                    pass


def execute(cmd: str, cwd: str, tty: Tty, shell: str = "") -> tuple[int, str]:
    executable = shutil.which(shell) if shell else None
    proc = subprocess.Popen(
        cmd, shell=True, cwd=cwd, executable=executable, stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, bufsize=1,
    )
    chunks: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        chunks.append(line)
        tty.write(line)
    proc.wait()
    return proc.returncode, "".join(chunks)


def _trim(text: str) -> str:
    if len(text) <= MAX_OUTPUT:
        return text
    return text[: MAX_OUTPUT // 2] + "\n… truncated …\n" + text[-MAX_OUTPUT // 2:]


def _handle_reads(step: dict, cfg, dry_run: bool = False) -> str:
    """Read the files a step asks for. Local and side-effect free, so no prompt."""
    from term_helper.context import read_file

    collected = []
    for path in step.get("reads", [])[:8]:  # ponytail: cap model fan-out
        render.note(f"  ↳ read {path}")
        if dry_run:
            collected.append(f"$ read {path}\n(not read: dry run)")
            continue
        body = read_file(path, int(cfg.get("read_max_lines", 200)),
                         int(cfg.get("read_max_bytes", 16384)))
        collected.append(f"$ read {path}\n{body}")
    return "\n\n".join(collected)


def run_plan(cfg, messages: list[dict], result: dict, *, cwd: str, shell: str = "",
             dry_run: bool = False, assume_yes: bool = False,
             continue_fn=None) -> list[str]:
    """Confirm and run a plan. Returns the commands that actually executed."""
    tty = Tty()
    max_steps = int(cfg.get("max_steps", 8))
    executed: list[str] = []
    iterations = 0

    audit.record({"event": "plan", "steps": result.get("steps", [])})

    try:
        while True:
            iterations += 1
            outputs: list[str] = []
            stop = False

            for step in result.get("steps", []):
                cmd = step["cmd"]

                if cmd:
                    if len(executed) >= max_steps:
                        render.warn(f"stopped: reached max_steps ({max_steps})")
                        stop = True
                        break
                    render.note(f"\n▶ {cmd}")
                    if step.get("why"):
                        render.note(f"  {step['why']}")
                    if policy.classify(cmd) == policy.AUTO:
                        render.note("  (read-only)")
                    elif step.get("risk") == "destructive":
                        render.warn("  ! destructive")

                    if dry_run:
                        render.note("  (dry run: not executed)")
                        outputs.append(f"$ {cmd}\n(not executed)")
                        continue

                    if not assume_yes:
                        tty.write("  Run? [y/N] ")
                        line = tty.readline()
                        if line == "":        # EOF: never run an unreviewed command
                            stop = True
                            break
                        if line.strip().lower() != "y":
                            render.note("  (skipped)")
                            audit.record({"event": "skip", "cmd": cmd})
                            outputs.append(f"$ {cmd}\n(skipped)")
                            continue

                read_output = _handle_reads(step, cfg, dry_run)
                if read_output:
                    outputs.append(read_output)

                if cmd:
                    code, out = execute(cmd, cwd, tty, shell)
                    executed.append(cmd)
                    if out.strip():
                        render.note(f"  → exit {code}")
                    else:
                        render.note(f"  → exit {code}, no output")
                    audit.record({"event": "run", "cmd": cmd, "exit": code,
                                  "output": _trim(out)[:MAX_OUTPUT]})
                    outputs.append(f"$ {cmd}\n(exit {code})\n{_trim(out)}")

            if stop or not continue_fn or len(executed) >= max_steps or iterations >= max_steps:
                break

            messages.append({"role": "assistant", "content": json.dumps(result)})
            messages.append({
                "role": "user",
                "content": (
                    "step results:\n\n" + "\n\n".join(outputs) +
                    "\n\nIf the task is complete, reply with mode=\"answer\" and a short "
                    "summary. Otherwise reply with mode=\"plan\" and the next steps."
                ),
            })
            render.note("\n… continuing")
            try:
                result = continue_fn(messages)
            except Exception as exc:  # noqa: BLE001 - surface, then stop the loop
                render.warn(f"continuation failed: {exc}")
                break
            if result.get("mode") == "answer":
                tty.write("\n" + result.get("answer", "") + "\n")
                break
    finally:
        tty.close()

    return executed
