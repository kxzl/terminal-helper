"""Interactive setup: detect the machine, recommend a model, install everything.

`term-helper setup` is what install.sh runs. It is safe to re-run.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from term_helper import config, models, render, server, shells

RELEASES = "https://api.github.com/repos/ggml-org/llama.cpp/releases?per_page=1"

# Small -> large. Sizes and repos verified against the Hugging Face API.
CATALOG: list[dict] = [
    {
        "id": "tiny",
        "name": "Qwen3.5 2B",
        "repo": "unsloth/Qwen3.5-2B-GGUF",
        "file": "Qwen3.5-2B-Q4_K_M.gguf",
        "gb": 1.19,
        "ram_gb": 3,
        "vram_gb": 0,
        "note": "runs on anything, including a 4 GB box",
    },
    {
        "id": "small",
        "name": "Granite 4.1 3B",
        "repo": "ibm-granite/granite-4.1-3b-GGUF",
        "file": "granite-4.1-3b-Q4_K_M.gguf",
        "gb": 1.96,
        "ram_gb": 4,
        "vram_gb": 0,
        "note": "best documented JSON / tool-call reliability at this size",
    },
    {
        "id": "medium",
        "name": "Qwen2.5-Coder 7B",
        "repo": "Qwen/Qwen2.5-Coder-7B-Instruct-GGUF",
        "file": "qwen2.5-coder-7b-instruct-q4_k_m.gguf",
        "gb": 4.36,
        "ram_gb": 8,
        "vram_gb": 6,
        "note": "clear step up in shell accuracy; wants a GPU",
    },
    {
        "id": "large",
        "name": "Qwen2.5-Coder 14B",
        "repo": "Qwen/Qwen2.5-Coder-14B-Instruct-GGUF",
        "file": "qwen2.5-coder-14b-instruct-q4_k_m.gguf",
        "gb": 8.37,
        "ram_gb": 16,
        "vram_gb": 12,
        "note": "best quality; needs a 12 GB+ GPU to be quick",
    },
]


@dataclass
class Specs:
    ram_gb: int
    cores: int
    vram_gb: int
    gpu: str
    vulkan: bool


def _mem_total_gb() -> int:
    try:
        for line in Path("/proc/meminfo").read_text().splitlines():
            if line.startswith("MemTotal:"):
                return round(int(line.split()[1]) / 1048576)
    except OSError:
        pass
    return 0


def _gpu(binary: str | None) -> tuple[int, str]:
    if not binary:
        return 0, ""
    try:
        out = subprocess.run([binary, "--list-devices"], capture_output=True,
                             text=True, timeout=30).stdout
    except (OSError, subprocess.SubprocessError):
        return 0, ""
    best, name = 0, ""
    for line in out.splitlines():
        if ":" not in line or "MiB" not in line:
            continue
        match = re.search(r"(\d+)\s*MiB", line)
        if not match:
            continue
        total = int(match.group(1))
        if total > best:
            best = total
            name = line.split(":", 1)[1].split("(")[0].strip()
    return round(best / 1024), name


def detect(binary: str | None = None) -> Specs:
    icd = Path("/usr/share/vulkan/icd.d")
    vulkan = icd.is_dir() and any(icd.glob("*.json"))
    vram, gpu = _gpu(binary)
    return Specs(_mem_total_gb(), os.cpu_count() or 1, vram, gpu, vulkan)


def recommend(specs: Specs) -> str:
    if specs.vram_gb >= 12 and specs.ram_gb >= 16:
        return "large"
    if specs.vram_gb >= 6 and specs.ram_gb >= 8:
        return "medium"
    if specs.ram_gb >= 6:
        return "small"
    return "tiny"


def estimate(specs: Specs, entry: dict) -> str:
    if specs.vram_gb and entry["gb"] <= specs.vram_gb * 0.8:
        return "fits your GPU"
    rate = 25.0 / entry["gb"]          # rough CPU, memory-bandwidth bound
    return f"~{max(1, round(rate))} tok/s on CPU"


def _arch() -> str:
    machine = platform.machine().lower()
    if machine in ("x86_64", "amd64"):
        return "x64"
    if machine in ("aarch64", "arm64"):
        return "arm64"
    raise SystemExit(f"unsupported architecture: {machine}")


def _download(url: str, target: Path, label: str) -> None:
    request = urllib.request.Request(url, headers={"User-Agent": "term-helper"})
    with urllib.request.urlopen(request) as response, target.open("wb") as handle:
        total = int(response.headers.get("Content-Length") or 0)
        done = 0
        while chunk := response.read(1 << 20):
            handle.write(chunk)
            done += len(chunk)
            if total:
                print(f"\r  {label} {done * 100 // total:3d}%", end="", file=sys.stderr)
    print("\r" + " " * (len(label) + 8) + "\r", end="", file=sys.stderr)


def ensure_llama() -> str:
    """Return a llama-server path, downloading a prebuilt build if needed."""
    local = config.DATA_DIR / "llama.cpp" / "llama-server"
    if local.exists():
        return str(local)
    found = shutil.which("llama-server")
    if found:
        return found

    render.note("llama.cpp not found — downloading a prebuilt build")
    request = urllib.request.Request(RELEASES, headers={"User-Agent": "term-helper"})
    release = json.load(urllib.request.urlopen(request))[0]
    vulkan = detect().vulkan
    arch = _arch()
    suffix = f"bin-ubuntu-{'vulkan-' if vulkan else ''}{arch}.tar.gz"
    asset = next((a for a in release["assets"] if a["name"].endswith(suffix)), None)
    if asset is None:
        raise SystemExit(f"no prebuilt llama.cpp for {arch} (vulkan={vulkan})")

    with tempfile.TemporaryDirectory() as tmp:
        archive = Path(tmp) / "llama.tar.gz"
        _download(asset["browser_download_url"], archive, asset["name"])
        with tarfile.open(archive) as tar:
            tar.extractall(tmp, filter="data")
        src = next(p for p in Path(tmp).iterdir() if p.is_dir())
        dest = config.DATA_DIR / "llama.cpp"
        dest.mkdir(parents=True, exist_ok=True)
        for item in src.iterdir():
            shutil.move(str(item), str(dest / item.name))
    render.note(f"llama.cpp {release['tag_name']} → {dest}")
    return str(dest / "llama-server")


def choose(specs: Specs, assume_yes: bool, forced: str | None) -> dict:
    pick = forced or recommend(specs)
    if forced:
        match = next((e for e in CATALOG if e["id"] == forced), None)
        if match is None:
            raise SystemExit(f"unknown model id '{forced}'")
        return match

    render.note("")
    render.note(f"  CPU      {specs.cores} cores")
    render.note(f"  RAM      {specs.ram_gb} GB")
    render.note(f"  GPU      {specs.gpu or 'none detected'}"
                + (f" ({specs.vram_gb} GB VRAM)" if specs.vram_gb else ""))
    render.note("")
    print("  Which model should it use?", file=sys.stderr)
    for i, entry in enumerate(CATALOG, 1):
        mark = "*" if entry["id"] == pick else " "
        star = "  <- recommended" if entry["id"] == pick else ""
        print(f"   {mark} {i}) {entry['name']:22} {entry['gb']:5.1f} GB   "
              f"{estimate(specs, entry):20} {entry['note']}{star}", file=sys.stderr)
    print(file=sys.stderr)

    if assume_yes:
        render.note(f"using the recommendation: {pick}")
        return next(e for e in CATALOG if e["id"] == pick)

    while True:
        answer = input(f"  Choose [1-{len(CATALOG)}] (Enter = recommended): ").strip()
        if not answer:
            return next(e for e in CATALOG if e["id"] == pick)
        if answer.isdigit() and 1 <= int(answer) <= len(CATALOG):
            return CATALOG[int(answer) - 1]
        if any(e["id"] == answer for e in CATALOG):
            return next(e for e in CATALOG if e["id"] == answer)
        print("  please pick a number", file=sys.stderr)


def write_config(entry: dict, specs: Specs) -> Path:
    on_gpu = specs.vram_gb >= 2
    model_name = entry["file"][:-5]
    text = f"""\
# term_helper configuration — written by `term-helper setup`.

[general]
llama_server = ""
max_steps = 8
history_lines = 15
history_max_chars = 200
read_max_lines = 200
read_max_bytes = 16384
deep_max_tokens = 4096
web_search = false
kagi_api_key = ""
search_results = 5

[server.suggest]
base_url = "http://127.0.0.1:8080"
model = "{model_name}"
extra_args = ["-ngl", "{99 if on_gpu else 0}", "--ctx-size", "{8192 if on_gpu else 4096}"]

[models]
"""
    config.CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    config.CONFIG_PATH.write_text(text, encoding="utf-8")
    return config.CONFIG_PATH


def cmd_setup(args) -> int:
    config.ensure_dirs()
    binary = ensure_llama()
    specs = detect(binary)
    entry = choose(specs, args.yes, args.model)

    target = models.models_dir() / entry["file"]
    if target.exists():
        render.note(f"model already present: {target}")
    else:
        render.note(f"downloading {entry['name']} ({entry['gb']} GB) — this can take a while")
        try:
            models.pull(f"hf:{entry['repo']}/{entry['file']}", entry["file"])
        except Exception as exc:  # noqa: BLE001 - network, disk, whatever
            render.error(f"download failed: {exc}")
            render.note("nothing was installed; re-run `term-helper setup` to retry")
            return 1

    path = write_config(entry, specs)
    render.note(f"config: {path}")
    config.ensure_api_key()

    installed = shells.install(args.shells)
    render.note(f"shims: {', '.join(installed) or 'none detected'}")

    cfg = config.load()
    units = []
    for name in cfg.roles:
        try:
            units.append(server.write_unit(cfg, name))
        except (FileNotFoundError, ValueError) as exc:
            render.warn(f"skipping {name} unit: {exc}")
    if units:
        server.systemctl("daemon-reload")
        if server.unit_path("suggest").exists():
            server.systemctl("enable", cfg.role("suggest").systemd_unit)

    render.note("")
    render.note("done. next:")
    render.note("  1. restart your shell (or source your rc file)")
    render.note("  2. press Ctrl-G at the prompt")
    render.note("  3. run `term-helper doctor` if anything looks off")
    return 0
