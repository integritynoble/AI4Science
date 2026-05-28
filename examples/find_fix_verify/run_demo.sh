#!/usr/bin/env bash
# Agentic find → fix → verify demo.
#
# Drives a single `ai4science chat` session that:
#   1. delegates to the physics-reviewer sub-agent to AUDIT the artifacts
#   2. has the main agent EDIT spec.md to fix the top issue it found
#   3. runs the pwm_validate MCP tool to VERIFY everything still passes
#
# This is the architecture in miniature: the LLM agent drafts/edits, a
# specialized sub-agent critiques, and the deterministic checks confirm —
# no LLM in the verification path.
#
# PREREQS (unlike the deterministic compute_demo, this makes real LLM calls):
#   - `pip install -e ".[claude]"` with the venv active
#   - the `claude` CLI on PATH, authed via `claude login` OR ANTHROPIC_API_KEY
#
# Output is non-deterministic (it's an LLM) — the exact issue found and the
# wording will vary run to run. The shipped CASSI example intentionally
# contains a physical inconsistency (a "zero-padded reflective" boundary —
# those modes are contradictory) plus a tolerance-vs-noise mismatch, so the
# reviewer reliably has something real to catch.
#
# Usage:  bash examples/find_fix_verify/run_demo.sh
set -euo pipefail

WORK="$(mktemp -d)"
echo "Scratch workspace: $WORK"
cd "$WORK"

ai4science init demo >/dev/null
cd demo

echo
echo "── Before ─────────────────────────────────────────────────────────────"
grep -E "boundary_conditions|tolerance_epsilon|noise_sigma" spec.md || true
echo

echo "── Agentic session: find → fix → verify ──────────────────────────────"
ai4science chat --yes <<'PROMPTS'
Delegate to the physics-reviewer sub-agent to audit spec.md and benchmark.md for the single most important physical inconsistency. Summarize just the top issue in two sentences.
Based on that finding, make ONE concrete Edit to fix it (pick the most defensible fix), then tell me exactly what you changed in one sentence.
Run the pwm_validate MCP tool and confirm in one line that all artifacts still pass after your edit.
/exit
PROMPTS

echo
echo "── After ──────────────────────────────────────────────────────────────"
grep -E "boundary_conditions|tolerance_epsilon|noise_sigma" spec.md || true
echo
echo "── Independent re-validation ──────────────────────────────────────────"
ai4science validate
echo
echo "Done. Scratch workspace (delete when finished): $WORK"
