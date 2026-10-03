#!/bin/sh
# Install or upgrade term-helper: link the launcher onto PATH, then wire the
# shims, systemd unit and config. Safe to re-run.
set -e
self=$0
case $self in
  */*) ;;
  *) self=$(command -v -- "$self" 2>/dev/null || echo "$self") ;;
esac
root=$(CDPATH= cd -- "$(dirname -- "$self")" && pwd)
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
