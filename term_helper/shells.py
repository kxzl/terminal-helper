"""Per-shell Shims: read the current buffer, call the Core, write text back."""

from __future__ import annotations

import shutil
from pathlib import Path

from term_helper import config

BEGIN = "# >>> term-helper >>>"
END = "# <<< term-helper <<<"

FISH = r"""# term-helper — fish shim
function __term_helper_ask --description 'Ask the local model about the current command line'
    set -l __th_buf (commandline -b)
    set -l __th_out (TERM_HELPER_SHELL=fish term-helper ask --shell fish --cwd "$PWD" --buffer "$__th_buf" $argv)
    # Commands the helper ran come back on stdout; record them so Ctrl-R finds them.
    for __th_cmd in $__th_out
        history append -- "$__th_cmd"
    end
    commandline -f repaint
end
# Ctrl-G asks; Ctrl-Y asks with the larger budget. Both are control codes, so
# they work on any keyboard layout (no Shift needed).
bind \cg __term_helper_ask
bind \cy '__term_helper_ask --deep'
# Alt-; / Alt-: also work where the layout and terminal pass Alt through.
bind \e\; __term_helper_ask
bind \e\: '__term_helper_ask --deep'
"""

ZSH = r"""# term-helper — zsh shim
term_helper_ask() {
  local buf="$BUFFER" out cmd
  out=$(TERM_HELPER_SHELL=zsh term-helper ask --shell zsh --cwd "$PWD" --buffer "$buf" "$@")
  zle -I
  # Commands the helper ran come back on stdout; record them for Ctrl-R.
  for cmd in ${(f)out}; do
    [[ -n "$cmd" ]] && print -s -- "$cmd"
  done
  zle redisplay
}
term_helper_ask_deep() { term_helper_ask --deep }
zle -N term_helper_ask
zle -N term_helper_ask_deep
# Ctrl-G asks; Ctrl-Y asks with the larger budget. Both are control codes, so
# they work on any keyboard layout (no Shift needed).
bindkey '^G' term_helper_ask
bindkey '^Y' term_helper_ask_deep
# Alt-; / Alt-: also work where the layout and terminal pass Alt through.
bindkey '^[;' term_helper_ask
bindkey '^[:' term_helper_ask_deep
"""

BASH = r"""# term-helper — bash shim
term_helper_ask() {
  local buf="$READLINE_LINE" out cmd
  out=$(TERM_HELPER_SHELL=bash term-helper ask --shell bash --cwd "$PWD" --buffer "$buf" "$@")
  # Commands the helper ran come back on stdout; record them for Ctrl-R.
  while IFS= read -r cmd; do
    [[ -n "$cmd" ]] && history -s -- "$cmd"
  done <<< "$out"
}
# Ctrl-G asks; Ctrl-Y asks with the larger budget. Both are control codes, so
# they work on any keyboard layout (no Shift needed).
bind -x '"\C-g": term_helper_ask'
bind -x '"\C-y": term_helper_ask --deep'
# Alt-; / Alt-: also work where the layout and terminal pass Alt through.
bind -x '"\e;": term_helper_ask'
bind -x '"\e:": term_helper_ask --deep'
"""

SHIMS = {"fish": FISH, "zsh": ZSH, "bash": BASH}


def rc_path(shell: str) -> Path:
    if shell == "fish":
        return Path.home() / ".config" / "fish" / "config.fish"
    return Path.home() / {"zsh": ".zshrc", "bash": ".bashrc"}[shell]


def available() -> list[str]:
    return [shell for shell in SHIMS if shutil.which(shell)]


def shim_text(shell: str) -> str:
    return SHIMS[shell]


def _block(shell: str, shim_file: Path) -> str:
    if shell == "fish":
        body = f"if test -f {shim_file}\n    source {shim_file}\nend"
    else:
        body = f"[ -f {shim_file} ] && source {shim_file}"
    return f"{BEGIN}\n{body}\n{END}\n"


def install(shells: list[str] | None = None) -> list[str]:
    selected = shells or available()
    shim_dir = config.DATA_DIR / "shims"
    shim_dir.mkdir(parents=True, exist_ok=True)
    done = []
    for shell in selected:
        if shell not in SHIMS:
            continue
        shim_file = shim_dir / f"term_helper.{shell}"
        shim_file.write_text(SHIMS[shell], encoding="utf-8")
        rc = rc_path(shell)
        rc.parent.mkdir(parents=True, exist_ok=True)
        existing = rc.read_text(encoding="utf-8") if rc.exists() else ""
        if BEGIN not in existing:
            rc.write_text(existing + ("\n" if existing and not existing.endswith("\n") else "")
                          + _block(shell, shim_file), encoding="utf-8")
        done.append(shell)
    return done


def uninstall() -> list[str]:
    done = []
    for shell in SHIMS:
        rc = rc_path(shell)
        if not rc.exists():
            continue
        lines = rc.read_text(encoding="utf-8").splitlines(keepends=True)
        if BEGIN not in "".join(lines):
            continue
        out, skipping = [], False
        for line in lines:
            if line.strip() == BEGIN:
                skipping = True
                continue
            if line.strip() == END:
                skipping = False
                continue
            if not skipping:
                out.append(line)
        rc.write_text("".join(out).rstrip() + "\n", encoding="utf-8")
        done.append(shell)
    return done
