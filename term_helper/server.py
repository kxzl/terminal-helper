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
ExecStart={binary} -m {model_path} --host {host} --port {port} {extra}
Restart=on-failure
RestartSec=3
StandardOutput=append:{log}
StandardError=append:{log}

[Install]
WantedBy=default.target
"""


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
    host = role.base_url.split("://", 1)[-1]
    return host.rsplit(":", 1)[0], role.port


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
    config.ensure_dirs()
    text = UNIT_TEMPLATE.format(
        name=name,
        model=role.model,
        binary=shlex.quote(cfg.llama_server),
        model_path=shlex.quote(str(model_path)),
        host=host,
        port=port,
        extra=" ".join(shlex.quote(a) for a in role.extra_args),
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
        [cfg.llama_server, "-m", str(model_path), "--host", host, "--port", str(port),
         *role.extra_args],
        stdout=log, stderr=log, start_new_session=True,
    )
    (config.PID_DIR / f"{role.name}.pid").write_text(str(proc.pid))


def start(cfg, name: str, wait: float = 30.0) -> bool:
    role = cfg.role(name)
    if health(role.base_url):
        return True
    if unit_path(name).exists() and has_systemd():
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
