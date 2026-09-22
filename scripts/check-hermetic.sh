#!/usr/bin/env bash
# Hermeticity gate for this repo, run from outside any existing environment.
#
# The contract: a fresh virtualenv plus `pip install -e ".[dev]"` and nothing
# else must be enough to COLLECT the whole test suite with zero errors. Tests
# that need an out-of-repo sibling (pwm_control_plane) or a host service
# (podman) must skip, not fail to import.
#
# Usage:  scripts/check-hermetic.sh [venv-dir]
# Exits non-zero, and prints the offending ERROR lines, if collection is dirty.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${1:-$(mktemp -d)/venv}"

echo "== fresh venv: $VENV"
python3 -m venv "$VENV"
"$VENV/bin/python" -m pip install --quiet --upgrade pip

echo "== pip install -e \".[dev]\""
"$VENV/bin/python" -m pip install --quiet -e "$REPO[dev]"

echo "== pytest --collect-only -q"
out="$(mktemp)"
cd "$REPO"
set +e
"$VENV/bin/python" -m pytest --collect-only -q >"$out" 2>&1
set -e
tail -n 5 "$out"

errors="$(grep -cE '^ERROR ' "$out" || true)"
if [ "${errors:-0}" -ne 0 ]; then
  echo
  echo "FAIL: $errors module(s) failed to collect in a fresh [dev] venv:"
  grep -E '^ERROR ' "$out"
  echo
  grep -E '^E +(ModuleNotFoundError|ImportError)' "$out" | sort -u
  exit 1
fi

collected="$(grep -oE '[0-9]+ tests collected' "$out" | tail -n 1)"
echo "OK: 0 collection errors (${collected:-count not reported})"
