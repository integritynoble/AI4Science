#!/usr/bin/env bash
# Model-selection demo — choose the model like Claude Code.
#
# Three ways to pick the model, plus a live in-session switch:
#   1. --model / -m flag        (ai4science --model opus  |  ai4science chat -m opus)
#   2. AI4SCIENCE_MODEL env      (export AI4SCIENCE_MODEL=opus)
#   3. /model <name> in-session  (switch live mid-conversation, via the SDK's set_model)
#
# This script drives the in-session path non-interactively (slash commands only,
# no LLM turns) so it's quick and deterministic. It needs the chat agent: the
# [claude] extra + the `claude` CLI (`claude login`).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Gate: the chat agent must be installed + authed.
if ! python -c "from ai4science.agents import ClaudeAgent; import sys; sys.exit(0 if ClaudeAgent().is_available() else 1)" 2>/dev/null; then
  echo "Chat agent not available. Enable it:"
  echo "  pip install 'pwm-ai4science[claude]'   # (default in the installer)"
  echo "  npm install -g @anthropic-ai/claude-code && claude login"
  exit 0
fi

WS="$(mktemp -d)"; cd "$WS"
echo "Scratch workspace: $WS"
echo

echo "── Start on --model sonnet, then switch live with /model ──────────────"
# /model (show) → /model haiku (switch) → /model (show) → /exit. No LLM turn
# is needed: slash commands are handled locally; set_model flips the model.
printf '/model\n/model haiku\n/model\n/exit\n' \
  | ai4science --model sonnet 2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -E "model:|model →"
echo

cat <<'EOF'
── The other two ways ─────────────────────────────────────────────────
  # flag, whole session:
  ai4science --model opus            # bare command → chat on opus
  ai4science chat -m sonnet          # the chat subcommand

  # env, whole session:
  export AI4SCIENCE_MODEL=haiku
  ai4science                         # picks up the env default

Names: opus, sonnet, haiku, or a full model id (e.g. claude-opus-4-1-...).
EOF
echo "Done. Scratch dir (delete when finished): $WS"
