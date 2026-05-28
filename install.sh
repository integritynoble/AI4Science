#!/usr/bin/env bash
# AI4Science installer — one-line install, no root / pipx / system packages.
#
#   curl -fsSL https://raw.githubusercontent.com/integritynoble/AI4Science/main/install.sh | bash
#
# Creates an isolated venv under ~/.ai4science and links the `ai4science`
# command into ~/.local/bin. Works on locked-down HPC login nodes.
#
# Env overrides:
#   AI4SCIENCE_HOME=<dir>     install location (default ~/.ai4science)
#   AI4SCIENCE_BIN=<dir>      where to link the command (default ~/.local/bin)
#   AI4SCIENCE_WITH_CLAUDE=1  also install the [claude] chat-agent extra
#   AI4SCIENCE_REF=<spec>     override the install source (pip requirement)
set -euo pipefail

PKG="pwm-ai4science"
GIT_URL="git+https://github.com/integritynoble/AI4Science.git"
INSTALL_DIR="${AI4SCIENCE_HOME:-$HOME/.ai4science}"
VENV="$INSTALL_DIR/venv"
BIN_DIR="${AI4SCIENCE_BIN:-$HOME/.local/bin}"
WITH_CLAUDE="${AI4SCIENCE_WITH_CLAUDE:-0}"

say()  { printf '\033[36m▸\033[0m %s\n' "$*"; }
ok()   { printf '\033[32m✓\033[0m %s\n' "$*"; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

say "Installing AI4Science (command: ai4science)…"

# 1. Find a Python >= 3.10.
find_python() {
  for c in python3.13 python3.12 python3.11 python3.10 python3 python; do
    command -v "$c" >/dev/null 2>&1 || continue
    "$c" - <<'PYEOF' >/dev/null 2>&1 || continue
import sys
raise SystemExit(0 if sys.version_info[:2] >= (3, 10) else 1)
PYEOF
    echo "$c"; return 0
  done
  return 1
}
PY="$(find_python)" || die "Python >= 3.10 not found on PATH. On an HPC cluster try: module load python/3.11"
ok "Using $("$PY" --version 2>&1) ($(command -v "$PY"))"

# 2. Isolated venv.
say "Creating venv at $VENV"
"$PY" -m venv "$VENV" || die "could not create venv (is python3-venv available?)"
"$VENV/bin/pip" install --quiet --upgrade pip >/dev/null

# 3. Install — PyPI first, fall back to GitHub (works before the PyPI release).
extra=""; [ "$WITH_CLAUDE" = "1" ] && extra="[claude]"
if [ -n "${AI4SCIENCE_REF:-}" ]; then
  say "Installing from AI4SCIENCE_REF=$AI4SCIENCE_REF"
  "$VENV/bin/pip" install --quiet "$AI4SCIENCE_REF" || die "install failed"
elif "$VENV/bin/pip" install --quiet "${PKG}${extra}" 2>/dev/null; then
  ok "Installed $PKG from PyPI"
else
  say "PyPI unavailable; installing from GitHub…"
  src="$GIT_URL"; [ -n "$extra" ] && src="${GIT_URL}#egg=${PKG}${extra}"
  "$VENV/bin/pip" install --quiet "$src" || die "install from GitHub failed"
  ok "Installed $PKG from GitHub"
fi

# 4. Expose the command on PATH.
mkdir -p "$BIN_DIR"
ln -sf "$VENV/bin/ai4science" "$BIN_DIR/ai4science"
ok "Linked $BIN_DIR/ai4science"

VER="$("$VENV/bin/ai4science" version 2>/dev/null || echo "ai4science")"
ok "Installed: $VER"

# 5. PATH guidance.
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    printf '\n\033[33m%s is not on your PATH.\033[0m Add this (and put it in ~/.bashrc):\n' "$BIN_DIR"
    printf '    export PATH="%s:$PATH"\n' "$BIN_DIR"
    ;;
esac

cat <<EOF

Done. Try:
    ai4science --help
    ai4science init my-first-contribution
$([ "$WITH_CLAUDE" != "1" ] && printf '\nFor the chat agent:  AI4SCIENCE_WITH_CLAUDE=1 curl -fsSL <this-url> | bash\n(+ the `claude` CLI: npm install -g @anthropic-ai/claude-code)')
EOF
