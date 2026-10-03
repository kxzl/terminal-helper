#!/bin/sh
# Uninstall term-helper: remove the shell shims, the systemd unit and the
# launcher symlink. Your config and downloaded models are left in place.
set -e
self=$0
case $self in
  */*) ;;
  *) self=$(command -v -- "$self" 2>/dev/null || echo "$self") ;;
esac
root=$(CDPATH= cd -- "$(dirname -- "$self")" 2>/dev/null && pwd || echo "")

# Run from PATH if installed, otherwise straight from this checkout.
if command -v term-helper >/dev/null 2>&1; then
  term-helper uninstall
elif [ -x "$root/bin/term-helper" ]; then
  "$root/bin/term-helper" uninstall
else
  echo "term-helper is not on PATH; nothing to uninstall" >&2
fi

bindir="${HOME}/.local/bin"
if [ -L "$bindir/term-helper" ]; then
  rm -f "$bindir/term-helper"
  echo "removed $bindir/term-helper"
fi
