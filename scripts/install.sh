#!/bin/sh
# AI4Science installer — the Claude Code pattern:
#
#   curl -fsSL https://physicsworldmodel.org/install.sh | bash
#
# Installs the `ai4science` CLI (package pwm-ai4science, with the [claude]
# extra so `--mode claude-code` can run the real Claude Code engine).
# Sources from GitHub (integritynoble/AI4Science). Safe to re-run (upgrades).
set -e

SPEC="pwm-ai4science[claude] @ git+https://github.com/integritynoble/AI4Science.git"

say() { printf '%s\n' "$*"; }
die() { printf 'install.sh: %s\n' "$*" >&2; exit 1; }

# ── python ≥ 3.10 ──────────────────────────────────────────────────────────
PY=""
for c in python3 python; do
  if command -v "$c" >/dev/null 2>&1; then
    if "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
      PY="$c"; break
    fi
  fi
done
[ -n "$PY" ] || die "python >= 3.10 is required (install it, then re-run)"

say "▸ installing AI4Science (pwm-ai4science[claude]) …"

# ── install: venv > pipx > pip --user ──────────────────────────────────────
if [ -n "${VIRTUAL_ENV:-}" ]; then
  "$PY" -m pip install --upgrade "$SPEC"
elif command -v pipx >/dev/null 2>&1; then
  pipx install --force "$SPEC"
else
  "$PY" -m pip install --user --upgrade "$SPEC" 2>/dev/null \
    || "$PY" -m pip install --user --upgrade --break-system-packages "$SPEC" \
    || die "pip install failed — try: pipx install '$SPEC'"
fi

# ── PATH check ─────────────────────────────────────────────────────────────
if ! command -v ai4science >/dev/null 2>&1; then
  case ":$PATH:" in
    *":$HOME/.local/bin:"*) ;;
    *) say "▸ note: add ~/.local/bin to your PATH, e.g.:"
       say "    export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
  esac
fi

say ""
say "✓ AI4Science installed."
say ""
say "Next steps (like Claude Code):"
say "  1.  ai4science login        # browser approval on physicsworldmodel.org"
say "                              # (no API key, no wallet private key — ever)"
say "  2.  ai4science              # start chatting; /mode picks an agent"
say ""
say "Optional engines: npm i -g @anthropic-ai/claude-code (claude-code mode),"
say "npm i -g @openai/codex (codex mode). Docs: https://physicsworldmodel.org/manual"
