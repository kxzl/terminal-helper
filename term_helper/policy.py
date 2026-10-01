"""Allowlist classification.

The Core decides whether a Step may Auto-run. The model's `risk` field is never
trusted (see docs/adr/0003-helper-enforces-allowlist.md).
"""

from __future__ import annotations

import os
import re
import shlex

AUTO = "auto"
ASK = "ask"

# Force ASK: anything that runs another command or elevates privileges.
WRAPPERS = {
    "sudo", "su", "doas", "pkexec", "env", "printenv", "nice", "ionice", "timeout",
    "watch", "xargs", "nohup", "setsid", "stdbuf", "eval", "exec", "command",
    "sh", "bash", "zsh", "fish", "dash", "ksh", "csh", "tcsh", "python", "python3",
    "perl", "ruby", "node", "deno", "bun", "php", "lua", "awk", "gawk", "nawk",
    "make", "ssh", "scp", "sftp", "rsync", "nc", "netcat", "ncat", "telnet", "socat",
    "ssh-keygen", "openssl", "gpg", "reboot", "shutdown", "poweroff", "halt", "init",
    "systemd-run", "kill", "pkill", "killall", "crontab", "at", "batch", "mount",
    "umount", "modprobe", "insmod", "rmmod", "sysctl", "useradd", "usermod", "userdel",
    "groupadd", "passwd", "chsh", "chfn", "iptables", "nft", "ufw", "firewall-cmd",
    "xdg-open", "gio", "open",
}

# Side-effect-free commands.
PURE_READ = {
    "ls", "pwd", "cat", "head", "tail", "tac", "rev", "grep", "egrep", "fgrep", "rg",
    "ag", "fd", "find", "file", "stat", "wc", "sort", "uniq", "cut", "tr", "column",
    "nl", "fold", "strings", "xxd", "od", "hexdump", "sha256sum", "sha1sum", "md5sum",
    "cksum", "diff", "cmp", "comm", "join", "paste", "tree", "realpath", "readlink",
    "basename", "dirname", "which", "whereis", "whatis", "apropos", "type", "man",
    "info", "echo", "printf", "seq", "date", "cal", "uptime", "nproc", "arch", "uname",
    "hostname", "hostnamectl", "whoami", "id", "groups", "users", "who", "w", "tty",
    "locale", "localectl", "timedatectl", "free", "df", "du", "lsblk", "blkid",
    "lscpu", "lsmem", "lsusb", "lspci", "lsmod", "findmnt", "ps", "pgrep", "pidof",
    "lsof", "ss", "ifconfig", "route", "arp", "ping", "traceroute", "tracepath", "dig",
    "host", "nslookup", "getent", "jq", "yq", "zcat", "dmesg", "vmstat", "journalctl",
    "sed",
}

# git subcommands that only read.
GIT_READ = {
    "status", "log", "diff", "show", "rev-parse", "ls-files", "blame", "shortlog",
    "describe", "rev-list", "cat-file", "whatchanged",
}
# git subcommands that read only when given no arguments (branch/tag/stash list).
GIT_BARE_SAFE = {"branch", "tag", "remote", "stash", "worktree", "submodule", "reflog"}

DOCKER_READ = {"ps", "images", "logs", "inspect", "version", "info", "top", "stats",
               "diff", "history", "port", "events", "search"}
KUBECTL_READ = {"get", "describe", "logs", "version", "api-resources", "explain",
                "cluster-info", "top"}
SYSTEMCTL_READ = {"status", "is-active", "is-enabled", "is-failed", "show", "cat",
                  "list-units", "list-unit-files", "list-timers", "list-sockets",
                  "get-default", "--version"}

SUBCOMMAND_READ = {"systemctl": SYSTEMCTL_READ, "docker": DOCKER_READ,
                   "podman": DOCKER_READ, "kubectl": KUBECTL_READ}

# Flags that turn an otherwise read-only command into a write.
WRITE_FLAGS: dict[str, set[str]] = {
    "find": {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0", "-fls"},
    "sort": {"-o", "--output"},
    "xxd": {"-r"},
    "journalctl": {"--vacuum-time", "--vacuum-size", "--vacuum-files", "--rotate",
                   "--flush", "--sync", "--relinquish-var", "--setup-keys"},
    "dmesg": {"-C", "--clear", "-c"},
    "timedatectl": {"set-time", "set-timezone", "set-ntp", "set-local-rtc"},
    "localectl": {"set-keymap", "set-x11-keymap", "set-locale"},
    "hostnamectl": {"set-hostname", "set-chassis", "set-deployment", "set-location",
                    "set-icon-name"},
}

CURL_WRITE = {"-d", "--data", "--data-binary", "--data-raw", "--data-urlencode",
              "-F", "--form", "-T", "--upload-file", "-o", "--output", "-O",
              "--remote-name", "--json"}

# Shell constructs that are never Auto-run.
UNSAFE = re.compile(r"[;&<>\n`]|\$\(|\|\|")

# sed writes only with an in-place flag: -i, -Ei, -i.bak, --in-place[=...].
SED_INPLACE = re.compile(r"^-[A-Za-z]*i")

# Directories we trust for an explicitly pathed command (e.g. /usr/bin/ls).
BIN_DIRS = {"/bin", "/usr/bin", "/usr/local/bin", "/sbin", "/usr/sbin",
            "/usr/local/sbin", "/usr/libexec"}


def _name(token: str) -> str | None:
    """Executable name, or None if the path is somewhere we do not trust."""
    if "/" in token:
        if os.path.dirname(os.path.abspath(token)) not in BIN_DIRS:
            return None
    return os.path.basename(token)


def _flag_hit(token: str, flag: str) -> bool:
    return token == flag or token.startswith(flag + "=") or (
        flag.startswith("--") and token.startswith(flag)
    )


def _force_ask(tokens: list[str]) -> bool:
    name = _name(tokens[0])
    if name is None or name in WRAPPERS:
        return True
    args = tokens[1:]
    if name == "sed" and any(SED_INPLACE.match(t) or t.startswith("--in-place") for t in args):
        return True
    flags = WRITE_FLAGS.get(name)
    if flags and any(_flag_hit(t, f) for f in flags for t in args):
        return True
    return False


def _simple(tokens: list[str]) -> str:
    name = _name(tokens[0])
    if name is None or name in WRAPPERS:
        return ASK
    args = tokens[1:]

    if name == "git":
        sub = args[0] if args else ""
        if sub in GIT_READ:
            return AUTO
        if sub in GIT_BARE_SAFE:
            return AUTO if len(args) == 1 else ASK
        return ASK

    if name in SUBCOMMAND_READ:
        sub = args[0] if args else ""
        return AUTO if sub in SUBCOMMAND_READ[name] else ASK

    if name == "curl":
        if any(_flag_hit(a, w) for w in CURL_WRITE for a in args):
            return ASK
        if "-I" in args or "--head" in args:
            return AUTO
        if "-X" in args or "--request" in args:
            idx = args.index("-X") if "-X" in args else args.index("--request")
            method = args[idx + 1].upper() if idx + 1 < len(args) else ""
            return AUTO if method == "GET" else ASK
        return ASK

    if name == "ip":
        mutating = {"set", "add", "del", "delete", "change", "flush", "replace", "append"}
        safe = {"a", "addr", "address", "link", "route", "r", "neigh", "n", "rule", "-br", "-j"}
        if any(a in mutating for a in args):
            return ASK
        return AUTO if any(a in safe for a in args) else ASK

    if name in PURE_READ:
        return AUTO
    return ASK


def classify(cmd: str) -> str:
    """Advisory: AUTO means read-only, ASK means the command changes something.

    Nothing auto-runs any more; every Step is confirmed. This only decides
    whether to show the "(read-only)" hint.
    """
    text = (cmd or "").strip()
    if not text:
        return ASK

    if UNSAFE.search(text):
        return ASK

    for segment in text.split("|"):
        segment = segment.strip()
        if not segment:
            return ASK
        try:
            tokens = shlex.split(segment)
        except ValueError:
            return ASK
        if not tokens:
            return ASK
        if _force_ask(tokens):
            return ASK
        if _simple(tokens) != AUTO:
            return ASK
    return AUTO
