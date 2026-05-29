#!/usr/bin/env bash
# Session-mode demo — switch between 'common' and 'research' like Claude Code's
# model switch.
#
#   common   : general Claude-Code-style assistant (the default)
#   research : drives the PWM pipeline — define problem → L1 principle → L2 spec
#              → L3 benchmark → L4 solution(s) → recommend journal/conference
#
# Three ways to pick the mode, plus a live in-session switch:
#   1. --mode flag             (ai4science --mode research)
#   2. AI4SCIENCE_MODE env      (export AI4SCIENCE_MODE=research)
#   3. /mode in-session         (picker menu, switches the next turn)
#
# This drives the in-session /mode picker non-interactively (slash commands
# only, no LLM turns) so it's quick and deterministic. Needs the chat agent:
# the [claude] extra + the `claude` CLI (`claude login`).
set -euo pipefail

if ! python -c "from ai4science.agents import ClaudeAgent; import sys; sys.exit(0 if ClaudeAgent().is_available() else 1)" 2>/dev/null; then
  echo "Chat agent not available. Enable it:"
  echo "  pip install 'pwm-ai4science[claude]'   # (default in the installer)"
  echo "  npm install -g @anthropic-ai/claude-code && claude login"
  exit 0
fi

WS="$(mktemp -d)"; cd "$WS"
echo "Scratch workspace: $WS"
echo

echo "── Launch in research mode, then switch live to common with /mode ─────"
# /mode (picker) → choose 1 (common) → /exit. No LLM turn needed.
printf '/mode\n1\n/exit\n' \
  | ai4science --mode research 2>&1 \
  | sed 's/\x1b\[[0-9;]*m//g' \
  | grep -E "mode:|Select a mode|^  [0-9]\.|mode →"
echo

cat <<'EOF'
── The other two ways ─────────────────────────────────────────────────
  ai4science --mode research      # bare command → chat in research mode
  ai4science chat --mode common   # the chat subcommand
  export AI4SCIENCE_MODE=research # env default for the session

Common = full Claude-Code assistant. Research = define → L1 principle → L2 spec
→ L3 benchmark → L4 solution(s) → recommend a journal/conference.
EOF
echo "Done. Scratch dir (delete when finished): $WS"
