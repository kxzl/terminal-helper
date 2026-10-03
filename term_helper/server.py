"""Server lifecycle for llama-server (systemd user units, subprocess fallback)."""

from __future__ import annotations

import os
import shlex
import subprocess
import time
from pathlib import Path

from term_helper import config, render
from term_helper.backend import health

UNIT_TEMPLATE = """\
[Unit]
Description=term_helper {name} model ({model})
After=network.target

[Service]
Type=simple
ExecStart={binary} -m {model_path}{api_key}{extra} --no-webui --no-slots --host {host} --port {port}
Restart=on-failure
RestartSec=3
StandardOutput=append:{log}
StandardError=append:{log}

# Hardening: loopback-only, no privilege escalation, minimal filesystem.
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={state_dir}
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictSUIDSGID=true
LockPersonality=true
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6
IPAddressDeny=any
IPAddressAllow=localhost
SystemCallArchitectures=native

[Install]
WantedBy=default.target
"""

# Hosts we are willing to bind llama-server to. Anything else is a
# misconfiguration that would expose an unauthenticated model server to the LAN.
LOOPBACK = {"127.0.0.1", "::1", "localhost"}

# Flags that would undo the local-only / no-tools guarantees. Refused in
# extra_args so a config edit cannot re-expose the server or give it shell tools.
FORBIDDEN = {
    "--tools", "--agent", "--mcp-servers", "--mcp-servers-config", "--media-path",
    "--slot-save-path", "--api-key", "--api-key-file", "--cors-origins",
    "--cors-methods", "--cors-headers",
}


def unit_dir() -> Path:
    return Path.home() / ".config" / "systemd" / "user"


def unit_path(name: str) -> Path:
    return unit_dir() / f"{config.APP}-{name}.service"


def systemctl(*args: str) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(["systemctl", "--user", *args], capture_output=True, text=True)
    except FileNotFoundError:
        return subprocess.CompletedProcess(args, 127, "", "systemctl not found")


def has_systemd() -> bool:
    return systemctl("is-system-running").returncode in (0, 1)


def _split_base(role) -> tuple[str, int]:
    host = role.base_url.split("://", 1)[-1].rsplit(":", 1)[0].strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if host not in LOOPBACK:
        raise ValueError(
            f"[server.{role.name}] base_url host '{host}' is not loopback; "
            "term-helper only binds llama-server to this machine "
            "(use 127.0.0.1 or ::1)"
        )
    return host, role.port


def _extra_args(role) -> list[str]:
    for arg in role.extra_args:
        if arg.split("=", 1)[0] in FORBIDDEN:
            raise ValueError(
                f"refusing {arg!r} in [server.{role.name}] extra_args: it weakens "
                "the local-only / no-tools guarantee"
            )
    return list(role.extra_args)


def _api_key_args() -> list[str]:
    if not config.api_key():
        return []
    return ["--api-key-file", str(config.API_KEY_PATH)]


def write_unit(cfg, name: str) -> Path:
    from term_helper.models import resolve

    role = cfg.role(name)
    model_path = resolve(cfg, role.model)
    if model_path is None:
        raise FileNotFoundError(
            f"model '{role.model}' not found; run 'term-helper models pull ...' "
            f"then set [server.{name}] model"
        )
    host, port = _split_base(role)
    extra = " ".join(shlex.quote(a) for a in _extra_args(role))
    api_key = " ".join(shlex.quote(a) for a in _api_key_args())
    config.ensure_dirs()
    text = UNIT_TEMPLATE.format(
        name=name,
        model=role.model,
        binary=shlex.quote(cfg.llama_server),
        model_path=shlex.quote(str(model_path)),
        host=host,
        port=port,
        extra=(" " + extra) if extra else "",
        api_key=(" " + api_key) if api_key else "",
        state_dir=config.STATE_DIR,
        log=config.LOG_DIR / f"{name}.log",
    )
    path = unit_path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _spawn(cfg, role) -> None:
    from term_helper.models import resolve

    model_path = resolve(cfg, role.model)
    if model_path is None:
        raise FileNotFoundError(f"model '{role.model}' not found")
    host, port = _split_base(role)
    config.ensure_dirs()
    log = (config.LOG_DIR / f"{role.name}.log").open("a", encoding="utf-8")
    proc = subprocess.Popen(
        [cfg.llama_server, "-m", str(model_path), *_api_key_args(), *_extra_args(role),
         "--no-webui", "--no-slots", "--host", host, "--port", str(port)],
        stdout=log, stderr=log, start_new_session=True,
    )
    (config.PID_DIR / f"{role.name}.pid").write_text(str(proc.pid))


def start(cfg, name: str, wait: float = 30.0) -> bool:
    role = cfg.role(name)
    if health(role.base_url):
        return True
    if unit_path(name).exists() and has_systemd():
        try:
            write_unit(cfg, name)  # refresh so the current API key is in the unit
        except Exception:  # noqa: BLE001 - keep the existing unit if this fails
            pass
        systemctl("start", role.systemd_unit)
    else:
        _spawn(cfg, role)
    deadline = time.monotonic() + wait
    with render.Status(prefix=f"loading {role.model}… ") as status:
        while time.monotonic() < deadline:
            if health(role.base_url):
                status.clear()
                return True
            time.sleep(0.5)
    return False


def stop(cfg, name: str) -> None:
    role = cfg.role(name)
    if unit_path(name).exists() and has_systemd():
        systemctl("stop", role.systemd_unit)
        return
    pid_file = config.PID_DIR / f"{role.name}.pid"
    if pid_file.exists():
        try:
            os.kill(int(pid_file.read_text().strip()), 15)
        except (OSError, ValueError):
            pass
        pid_file.unlink(missing_ok=True)


def schedule_idle_stop(cfg, name: str) -> None:
    """Stop an on-demand server after it has been idle for deep_idle_minutes."""
    minutes = int(cfg.get("deep_idle_minutes", 0) or 0)
    if name != "deep" or minutes <= 0:
        return
    config.ensure_dirs()
    stamp = config.PID_DIR / f"{name}.idle"
    token = str(time.time())
    stamp.write_text(token)
    script = (f"sleep {minutes * 60}; "
              f'[ "$(cat {stamp})" = "{token}" ] && term-helper server stop --deep')
    subprocess.Popen(["sh", "-c", script], start_new_session=True,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def status(cfg) -> list[tuple[str, str, bool]]:
    rows = []
    for name, role in cfg.roles.items():
        state = ""
        if unit_path(name).exists() and has_systemd():
            state = systemctl("is-active", role.systemd_unit).stdout.strip()
        rows.append((name, state or "n/a", health(role.base_url)))
    return rows
