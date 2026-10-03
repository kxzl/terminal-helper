#!/bin/sh
# Install or upgrade term-helper. Safe to re-run.
#
#   ./install.sh
#   curl -fsSL https://raw.githubusercontent.com/kxzl/terminal-helper/main/install.sh | sh
set -e

repo="${TERM_HELPER_REPO:-https://github.com/kxzl/terminal-helper.git}"
src="${TERM_HELPER_SRC:-${XDG_DATA_HOME:-$HOME/.local/share}/term-helper/src}"

# Find the checkout: next to this script, or fetch one when piped from a URL.
self=$0
case $self in
  */*) ;;
  *) self=$(command -v -- "$self" 2>/dev/null || echo "$self") ;;
esac
root=$(CDPATH= cd -- "$(dirname -- "$self")" 2>/dev/null && pwd || echo "")
if [ ! -x "$root/bin/term-helper" ]; then
  if command -v git >/dev/null 2>&1; then
    if [ -d "$src/.git" ]; then
      git -C "$src" pull --ff-only
    else
      rm -rf "$src"
      mkdir -p "$(dirname "$src")"
      git clone --depth 1 "$repo" "$src"
    fi
  else
    echo "git not found; downloading the source archive" >&2
    rm -rf "$src"
    mkdir -p "$src"
    archive="$src.tar.gz"
    url="${repo%.git}/archive/refs/heads/main.tar.gz"
    if command -v curl >/dev/null 2>&1; then
      curl -fsSL "$url" -o "$archive"
    else
      wget -qO "$archive" "$url"
    fi
    tar -xzf "$archive" -C "$src" --strip-components=1
    rm -f "$archive"
  fi
  root="$src"
fi

bindir="${HOME}/.local/bin"
mkdir -p "$bindir"
ln -sf "$root/bin/term-helper" "$bindir/term-helper"
echo "linked $bindir/term-helper"

config="${XDG_CONFIG_HOME:-$HOME/.config}/term-helper/config.toml"
if [ -f "$config" ]; then
  # Already set up: refresh shims, unit and key, keep your config and models.
  exec "$bindir/term-helper" install "$@"
fi
# First run: detect the machine and download a model.
exec "$bindir/term-helper" setup "$@"
