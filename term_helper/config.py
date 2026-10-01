"""Configuration loading for term_helper.

Single source of truth for paths and the TOML config. Python 3.11+ (tomllib).
"""

from __future__ import annotations

import os
import shutil
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

APP = "term-helper"


def _xdg(env: str, default: Path) -> Path:
    value = os.environ.get(env)
    return Path(value) if value else default


CONFIG_DIR = _xdg("XDG_CONFIG_HOME", Path.home() / ".config") / APP
STATE_DIR = _xdg("XDG_STATE_HOME", Path.home() / ".local" / "state") / APP
DATA_DIR = _xdg("XDG_DATA_HOME", Path.home() / ".local" / "share") / APP
CONFIG_PATH = CONFIG_DIR / "config.toml"
AUDIT_PATH = STATE_DIR / "audit.jsonl"
LOG_DIR = STATE_DIR / "log"
PID_DIR = STATE_DIR / "run"

DEFAULT_TOML = """\
# term_helper configuration
# See config.example.toml in the repository for documentation.

[general]
# Where llama-server lives. Empty means "look in the data dir, then $PATH".
llama_server = ""
max_steps = 8
history_lines = 15
history_max_chars = 200
read_max_lines = 200
read_max_bytes = 16384
# Token budget for the deep keybinding (Alt-:), which uses the same model.
deep_max_tokens = 4096

[server.suggest]
base_url = "http://127.0.0.1:8080"
model = "qwen2.5-coder-14b"
extra_args = ["-ngl", "99", "--ctx-size", "8192"]

[models]
# Explicit overrides, name -> absolute path to a .gguf file:
# qwen2.5-coder-14b = "/home/you/models/qwen2.5-coder-14b-q4_k_m.gguf"
"""


@dataclass
class ServerRole:
    name: str
    base_url: str
    model: str
    extra_args: list[str] = field(default_factory=list)

    @property
    def port(self) -> int:
        tail = self.base_url.rstrip("/").rsplit(":", 1)[-1]
        return int(tail) if tail.isdigit() else 8080

    @property
    def systemd_unit(self) -> str:
        return f"{APP}-{self.name}.service"


@dataclass
class Config:
    general: dict[str, Any]
    roles: dict[str, ServerRole]
    models: dict[str, str]
    path: Path

    def role(self, name: str) -> ServerRole:
        if name in self.roles:
            return self.roles[name]
        return self.roles["suggest"]

    def get(self, key: str, default: Any = None) -> Any:
        return self.general.get(key, default)

    @property
    def llama_server(self) -> str:
        explicit = self.general.get("llama_server") or ""
        if explicit:
            return os.path.expanduser(explicit)
        local = DATA_DIR / "llama.cpp" / "llama-server"
        if local.exists():
            return str(local)
        return shutil.which("llama-server") or "llama-server"


def default_config() -> Config:
    data = tomllib.loads(DEFAULT_TOML)
    return _from_dict(data, CONFIG_PATH)


def _from_dict(data: dict[str, Any], path: Path) -> Config:
    roles: dict[str, ServerRole] = {}
    for name, raw in data.get("server", {}).items():
        roles[name] = ServerRole(
            name=name,
            base_url=raw.get("base_url", "http://127.0.0.1:8080"),
            model=raw.get("model", ""),
            extra_args=list(raw.get("extra_args", [])),
        )
    if "suggest" not in roles:
        roles["suggest"] = ServerRole("suggest", "http://127.0.0.1:8080", "")
    return Config(
        general=dict(data.get("general", {})),
        roles=roles,
        models=dict(data.get("models", {})),
        path=path,
    )


def load() -> Config:
    if CONFIG_PATH.exists():
        with CONFIG_PATH.open("rb") as handle:
            return _from_dict(tomllib.load(handle), CONFIG_PATH)
    return default_config()


def write_default(force: bool = False) -> Path:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if CONFIG_PATH.exists() and not force:
        return CONFIG_PATH
    CONFIG_PATH.write_text(DEFAULT_TOML, encoding="utf-8")
    return CONFIG_PATH


def ensure_dirs() -> None:
    for directory in (CONFIG_DIR, STATE_DIR, LOG_DIR, PID_DIR, DATA_DIR):
        directory.mkdir(parents=True, exist_ok=True)
