#!/bin/sh
# Install term-helper: link the launcher onto PATH, then run the guided setup.
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
exec "$bindir/term-helper" setup "$@"
