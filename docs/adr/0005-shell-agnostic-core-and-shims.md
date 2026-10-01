# Shell-agnostic Core with thin per-shell Shims

The logic lives in one Python 3 stdlib program; each supported shell gets a tiny
Shim that knows only how to read and write its own command line (`commandline`
in fish, `zle`/`BUFFER` in zsh, `READLINE_LINE` in bash). Considered: a single
POSIX sh script (cannot manipulate any shell's line editor) and a per-shell
implementation (three copies of the logic). Consequence: adding a shell means
writing a Shim, not porting the tool, and the Python dependency is the one hard
requirement.
