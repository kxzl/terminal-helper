"""Command-line entry point for term-helper."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys

from term_helper import (audit, backend, config, context, contract, loop, models,
                         prompt, render, server, setup, shells)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="term-helper",
                                     description="Strictly local terminal helper")
    sub = parser.add_subparsers(dest="command")

    ask = sub.add_parser("ask", help="ask the local model about the current command line")
    ask.add_argument("--deep", action="store_true", help="use the larger token budget")
    ask.add_argument("--buffer", default="", help="the current command line")
    ask.add_argument("--cwd", default=os.getcwd())
    ask.add_argument("--shell", default=os.environ.get("TERM_HELPER_SHELL", ""))
    ask.add_argument("--dry-run", action="store_true", help="never auto-run")
    ask.add_argument("--yes", action="store_true", help="approve every step")
    ask.add_argument("--no-continue", action="store_true", help="single model turn")

    srv = sub.add_parser("server", help="manage llama-server")
    srv.add_argument("action", choices=["start", "stop", "restart", "status"])

    mdl = sub.add_parser("models", help="manage local GGUF models")
    mdl.add_argument("action", choices=["list", "pull"])
    mdl.add_argument("spec", nargs="?", help="https URL or hf:<org>/<repo>/<file.gguf>")
    mdl.add_argument("--name", default=None)

    log = sub.add_parser("log", help="show the audit log")
    log.add_argument("--tail", type=int, default=20)
    log.add_argument("--runs", action="store_true", help="only executed/inserted commands")

    cfg = sub.add_parser("config", help="inspect or edit configuration")
    cfg.add_argument("action", choices=["path", "init", "edit", "show"], default="show", nargs="?")

    sub.add_parser("doctor", help="check the installation")

    stp = sub.add_parser("setup", help="detect the machine, pick and download a model")
    stp.add_argument("--yes", action="store_true", help="accept the recommendation")
    stp.add_argument("--model", choices=[e["id"] for e in setup.CATALOG], default=None)
    stp.add_argument("--shell", action="append", dest="shells", choices=list(shells.SHIMS))

    inst = sub.add_parser("install", help="wire shims, units and config")
    inst.add_argument("--shell", action="append", dest="shells", choices=list(shells.SHIMS))
    sub.add_parser("uninstall", help="remove shims from shell rc files")

    shim = sub.add_parser("shim", help="print a shell shim")
    shim.add_argument("shell", choices=list(shells.SHIMS))

    sub.add_parser("keys", help="show what a keypress sends, to debug bindings")

    return parser


def _ensure_server(cfg, role_name: str) -> bool:
    role = cfg.role(role_name)
    if backend.health(role.base_url):
        return True
    render.note(f"starting {role_name} server ({role.model})…")
    try:
        if server.start(cfg, role_name):
            return True
    except Exception as exc:  # noqa: BLE001 - report, never traceback
        render.error(str(exc))
        return False
    render.error(f"could not reach {role.model} at {role.base_url}")
    render.note("hint: term-helper doctor")
    return False


def cmd_ask(args) -> int:
    cfg = config.load()
    config.ensure_dirs()
    role_name = "suggest"
    if role_name not in cfg.roles:
        render.error(f"no [server.{role_name}] in {config.CONFIG_PATH}")
        return 1
    role = cfg.role(role_name)
    max_tokens = int(cfg.get("deep_max_tokens", 4096)) if args.deep else 1024

    if not _ensure_server(cfg, role_name):
        return 1

    tty = loop.Tty()
    try:
        request = args.buffer.strip()
        if not request:
            request = prompt.LineEditor(tty).read("? ") or ""
    finally:
        tty.close()  # restore terminal modes even on Ctrl-C
    if not request:
        return 0

    messages = context.build_messages(cfg, shell=args.shell, cwd=args.cwd,
                                      buffer=args.buffer, request=request)

    def stream(status):
        return lambda chunk: status.update(render.preview(chunk))

    try:
        with render.Status() as status:
            raw = backend.chat(role, messages, on_token=stream(status),
                               max_tokens=max_tokens)
    except backend.BackendError as exc:
        render.error(str(exc))
        return 1

    try:
        result = contract.parse(raw)
    except Exception as exc:  # noqa: BLE001 - any malformed model output
        render.error(f"unusable model response: {exc}")
        audit.record({"event": "error", "error": str(exc), "raw": raw[:2000]})
        return 2

    audit.record({"event": "ask", "role": role_name, "request": request,
                  "mode": result["mode"]})

    if result["mode"] == "answer":
        print(result["answer"], file=sys.stderr)
        return 0

    def continue_fn(msgs: list[dict]) -> dict:
        with render.Status(prefix="thinking… ") as status:
            out = backend.chat(role, msgs, on_token=stream(status), max_tokens=max_tokens)
        return contract.parse(out)

    ran = loop.run_plan(
        cfg, messages, result, cwd=args.cwd, shell=args.shell,
        dry_run=args.dry_run, assume_yes=args.yes,
        continue_fn=None if args.no_continue else continue_fn,
    )
    for cmd in ran:  # stdout: the Shim records these in shell history
        print(cmd)
    return 0


def cmd_server(args) -> int:
    cfg = config.load()
    name = "suggest"
    if args.action == "start":
        ok = server.start(cfg, name)
        render.note("up" if ok else "failed to start")
        return 0 if ok else 1
    if args.action == "stop":
        server.stop(cfg, name)
        return 0
    if args.action == "restart":
        server.stop(cfg, name)
        return 0 if server.start(cfg, name) else 1
    for name, state, up in server.status(cfg):
        print(f"{name:8} {'up' if up else 'down':4} systemd={state}")
    return 0


def cmd_models(args) -> int:
    cfg = config.load()
    if args.action == "list":
        found = models.local()
        if not found:
            render.note(f"no models in {models.models_dir()} ({models.disk_usage()})")
        for path in found:
            print(f"{path.name:50} {path.stat().st_size >> 30} GiB")
        for name, path in cfg.models.items():
            print(f"{name:50} -> {path}")
        return 0
    if not args.spec:
        render.error("usage: term-helper models pull <url|hf:org/repo/file.gguf>")
        return 1
    try:
        models.pull(args.spec, args.name)
    except Exception as exc:  # noqa: BLE001
        render.error(str(exc))
        return 1
    return 0


def cmd_log(args) -> int:
    for entry in audit.tail(args.tail):
        if args.runs and entry.get("event") not in ("run", "insert"):
            continue
        if args.runs:
            print(f"{entry['ts']}  {entry.get('cmd', '')}")
        else:
            print(json.dumps(entry, ensure_ascii=False))
    return 0


def cmd_config(args) -> int:
    if args.action == "path":
        print(config.CONFIG_PATH)
        return 0
    if args.action == "init":
        render.note(f"wrote {config.write_default()}")
        return 0
    if args.action == "edit":
        config.write_default()
        editor = os.environ.get("EDITOR", "vi")
        return os.spawnvp(os.P_WAIT, editor, [editor, str(config.CONFIG_PATH)])
    if config.CONFIG_PATH.exists():
        print(config.CONFIG_PATH.read_text(encoding="utf-8"))
    else:
        render.note(f"no config at {config.CONFIG_PATH}; run 'term-helper config init'")
    return 0


def cmd_doctor(args) -> int:
    cfg = config.load()
    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok
        ok = ok and passed
        print(f"[{'ok' if passed else '--'}] {label}{('  ' + detail) if detail else ''}")

    check("python >= 3.11", sys.version_info >= (3, 11), sys.version.split()[0])
    binary = cfg.llama_server
    check("llama-server", shutil.which(binary) is not None or os.path.exists(binary), binary)
    check("config", config.CONFIG_PATH.exists(), str(config.CONFIG_PATH))
    for name, role in cfg.roles.items():
        path = models.resolve(cfg, role.model)
        check(f"model[{name}]", path is not None, f"{role.model} -> {path or 'missing'}")
        check(f"server[{name}]", backend.health(role.base_url), role.base_url)
    check("shims", bool(shells.available()), ", ".join(shells.available()))
    check("systemd --user", server.has_systemd())
    return 0 if ok else 1


def cmd_install(args) -> int:
    config.ensure_dirs()
    render.note(f"config: {config.write_default()}")
    done = shells.install(args.shells)
    render.note(f"shims: {', '.join(done) or 'none detected'}")

    cfg = config.load()
    units = []
    for name in cfg.roles:
        try:
            units.append(server.write_unit(cfg, name))
        except FileNotFoundError as exc:
            render.warn(f"skipping {name} unit: {exc}")
    if units:
        server.systemctl("daemon-reload")
        render.note(f"units: {', '.join(u.name for u in units)}")
        if server.unit_path("suggest").exists():
            server.systemctl("enable", cfg.role("suggest").systemd_unit)
            render.note("enabled term-helper-suggest.service")
    render.note("restart your shell, then press Alt-; at the prompt")
    return 0


def cmd_uninstall(args) -> int:
    done = shells.uninstall()
    for name in ("suggest",):
        unit = server.unit_path(name)
        if unit.exists():
            server.systemctl("disable", "--now", f"{config.APP}-{name}.service")
            unit.unlink(missing_ok=True)
    server.systemctl("daemon-reload")
    render.note(f"removed shims from: {', '.join(done) or 'none'}")
    render.note("config and models were left in place")
    return 0


def cmd_shim(args) -> int:
    print(shells.shim_text(args.shell), end="")
    return 0


def cmd_keys(args) -> int:
    """Read raw keypresses and print the sequence, to debug shell bindings."""
    import select
    import termios
    import tty

    if not sys.stdin.isatty():
        render.error("run this in an interactive terminal, not piped")
        return 1
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    render.note("press the key combo you want to bind (Ctrl-C to stop)")
    try:
        tty.setraw(fd)
        while True:
            first = os.read(fd, 1)
            if first == b"\x03":
                break
            seq = first
            while select.select([fd], [], [], 0.05)[0]:
                seq += os.read(fd, 1)
            print(f"{seq!r}  ->  fish key: {_fish_key(seq)}")
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)
    print()
    return 0


def _fish_key(seq: bytes) -> str:
    text = seq.decode("utf-8", "replace")
    if text.startswith("\x1b"):
        return "\\e" + text[1:]
    if len(text) == 1 and ord(text) < 32:
        return "\\c" + chr(ord(text) + 96)
    return text


HANDLERS = {
    "ask": cmd_ask,
    "server": cmd_server,
    "models": cmd_models,
    "log": cmd_log,
    "config": cmd_config,
    "doctor": cmd_doctor,
    "setup": setup.cmd_setup,
    "install": cmd_install,
    "uninstall": cmd_uninstall,
    "shim": cmd_shim,
    "keys": cmd_keys,
}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0
    return HANDLERS[args.command](args)
