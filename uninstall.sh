#!/bin/sh
# Uninstall term-helper: remove the shell shims, the systemd unit and the
# launcher symlink. Your config and downloaded models are left in place.
set -e
self=$0
case $self in
  */*) ;;
  *) self=$(command -v -- "$self" 2>/dev/null || echo "$self") ;;
esac
root=$(CDPATH= cd -- "$(dirname -- "$self")" && pwd)

# Run from PATH if installed, otherwise straight from this checkout.
if command -v term-helper >/dev/null 2>&1; then
  term-helper uninstall
else
  "$root/bin/term-helper" uninstall
fi

bindir="${HOME}/.local/bin"
if [ -L "$bindir/term-helper" ]; then
  rm -f "$bindir/term-helper"
  echo "removed $bindir/term-helper"
fi
