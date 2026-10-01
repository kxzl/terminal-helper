"""GGUF model discovery and download. Downloads are the only network use."""

from __future__ import annotations

import shutil
import sys
import urllib.request
from pathlib import Path

from term_helper import config, render


def models_dir() -> Path:
    directory = config.DATA_DIR / "models"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def local() -> list[Path]:
    return sorted(models_dir().glob("*.gguf"))


def resolve(cfg, name: str) -> Path | None:
    if not name:
        return None
    explicit = cfg.models.get(name)
    if explicit:
        path = Path(explicit).expanduser()
        return path if path.exists() else None
    exact = models_dir() / f"{name}.gguf"
    if exact.exists():
        return exact
    for candidate in sorted(models_dir().glob(f"{name}*")):
        return candidate
    return None


def _url(spec: str) -> str:
    if spec.startswith(("http://", "https://")):
        return spec
    if spec.startswith("hf:"):
        parts = spec[3:].split("/")
        if len(parts) == 3:
            org, repo, filename = parts
            return f"https://huggingface.co/{org}/{repo}/resolve/main/{filename}"
    raise ValueError("expected an https URL or hf:<org>/<repo>/<file.gguf>")


def pull(spec: str, name: str | None = None) -> Path:
    url = _url(spec)
    filename = name or url.rsplit("/", 1)[-1]
    if not filename.endswith(".gguf"):
        filename += ".gguf"
    target = models_dir() / filename
    part = target.with_suffix(target.suffix + ".part")
    render.note(f"downloading {url}")
    last = -1
    try:
        with urllib.request.urlopen(url) as response, part.open("wb") as handle:
            total = int(response.headers.get("Content-Length") or 0)
            done = 0
            while chunk := response.read(1 << 20):
                handle.write(chunk)
                done += len(chunk)
                if total:
                    pct = done * 100 // total
                    if pct != last:
                        last = pct
                        sys.stderr.write(f"\r\033[2m  {pct:3d}%  {done >> 20} MiB\033[0m")
                        sys.stderr.flush()
        sys.stderr.write("\r" + " " * 30 + "\r")
        part.replace(target)
    except BaseException:
        part.unlink(missing_ok=True)   # never leave a truncated .gguf behind
        raise
    render.note(f"saved {target} ({target.stat().st_size >> 20} MiB)")
    return target


def disk_usage() -> str:
    usage = shutil.disk_usage(models_dir())
    return f"{usage.used >> 30} GiB used, {usage.free >> 30} GiB free"
