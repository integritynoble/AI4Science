#!/usr/bin/env bash
# A developer environment that can RUN the suite, not merely collect it.
#
# `pip install -e ".[dev]"` is the hermeticity contract (see
# scripts/check-hermetic.sh) and, since the `[dev]` extra grew the eight
# `pwm-agent-*` packages and `claude-agent-sdk`, it is also enough to run all
# but a handful of tests. This script adds the two things pip cannot reach:
#
#   * `pwm_control_plane` — a sibling repo, deliberately NOT on PyPI. Every
#     test that needs it already does `pytest.importorskip("pwm_control_plane")`
#     (tests/test_control_plane_client.py:6), so without it they SKIP. They do
#     not fail. Installing it turns those skips into coverage.
#   * the `claude` CLI — npm, not pip. `sdk_repl.sdk_available()` wants it on
#     PATH, and the live tests (`SARSI_LIVE_TEST=1`) drive the real binary.
#     Nothing in the default suite fails without it: the two `sdk_available`
#     tests monkeypatch `shutil.which` and only need the SDK *package*.
#
# So: `[dev]` gives you a green suite; this gives you a complete one.
#
# Usage:
#   scripts/dev-venv.sh [venv-dir]
#
# Environment:
#   PWM_SIBLINGS   directory holding the sibling checkouts. Default: the parent
#                  of this repo, i.e. the usual side-by-side clone layout
#                  (.../AI4Science, .../pwm-control-plane, .../pwm-agent-*).
#                  Point it wherever yours live.
#   WITH_CLAUDE=0  skip the `claude` CLI check.
#
# Every sibling is OPTIONAL: a missing one is reported and skipped, never
# fatal. A developer with none of them still gets the `[dev]` environment.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="${1:-$REPO/.venv}"
SIBLINGS="${PWM_SIBLINGS:-$(dirname "$REPO")}"

say() { printf '\033[36m==\033[0m %s\n' "$*"; }
ok()  { printf '\033[32m✓\033[0m %s\n'  "$*"; }
warn(){ printf '\033[33m⚠\033[0m %s\n'  "$*"; }

if [ ! -d "$VENV" ]; then
  say "creating venv: $VENV"
  python3 -m venv "$VENV"
fi
PY="$VENV/bin/python"
[ -x "$PY" ] || PY="$VENV/Scripts/python.exe"   # Windows layout
"$PY" -m pip install --quiet --upgrade pip

say "pip install -e \"$REPO[dev]\""
"$PY" -m pip install --quiet -e "$REPO[dev]"
ok "core + dev extra (includes the 8 pwm-agent-* packages and claude-agent-sdk)"

# --- siblings that are not on PyPI ------------------------------------------
#
# Editable, because the point of having them as checkouts is to change them.
# The eight `pwm-agent-*` come from PyPI via `[dev]`; if you are DEVELOPING one
# of them, its checkout here overrides the released wheel — same-named dirs
# take precedence in the loop below.
install_editable() {          # install_editable <import-name> <dir-name>...
  local mod="$1"; shift
  local d
  for d in "$@"; do
    if [ -f "$SIBLINGS/$d/pyproject.toml" ] || [ -f "$SIBLINGS/$d/setup.py" ]; then
      say "editable: $SIBLINGS/$d"
      "$PY" -m pip install --quiet -e "$SIBLINGS/$d" && { ok "$mod"; return 0; }
      warn "$d failed to install — continuing"
      return 1
    fi
  done
  warn "$mod not found under $SIBLINGS (looked for: $*) — its tests will skip"
  return 0
}

install_editable pwm_control_plane pwm-control-plane pwm_control_plane control-plane

for a in research paper imaging drug cancer unified claude-gpu codex-gpu; do
  d="pwm-agent-$a"
  if [ -f "$SIBLINGS/$d/pyproject.toml" ]; then
    say "editable (overriding the PyPI wheel): $SIBLINGS/$d"
    "$PY" -m pip install --quiet -e "$SIBLINGS/$d" || warn "$d failed — keeping the wheel"
  fi
done

# --- the `claude` CLI --------------------------------------------------------
if [ "${WITH_CLAUDE:-1}" = "1" ]; then
  if command -v claude >/dev/null 2>&1; then
    ok "claude CLI on PATH: $(command -v claude)"
  else
    warn "claude CLI not on PATH. Nothing in the default suite needs it, but"
    warn "  \`ai4science chat\` and the SARSI_LIVE_TEST=1 runs do. Install with:"
    warn "      npm install -g @anthropic-ai/claude-code"
  fi
fi

echo
ok "ready:  $VENV/bin/python -m pytest"
"$PY" -m pip list 2>/dev/null | grep -E '^(pwm-|claude-agent-sdk)' || true
