#!/usr/bin/env bash
# End-to-end AI4Science compute-provider demo (Phase 0).
#
# Runs the full loop on one machine using a throwaway registry + inbox so it
# never touches your real ~/.config/ai4science:
#
#   register provider (wallet-bound)  →  init workspace  →  generate data
#   →  dispatch job  →  poller runs solver (GPU side)  →  judge verifies
#   →  credit lands on the wallet
#
# Prereqs: `pip install -e .` with the venv active (so `ai4science` and
# `python` are on PATH).
#
# Usage:
#   bash examples/compute_demo/run_demo.sh [WALLET_ADDRESS]
#
# WALLET_ADDRESS defaults to a demo address. Pass your own 0x… to bind it.
set -euo pipefail

WALLET="${1:-0xDe0000000000000000000000000000000000bEEF}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WORK="$(mktemp -d)"
export AI4SCIENCE_COMPUTE_REGISTRY="$WORK/registry.json"
JOBS="$WORK/compute_jobs"
echo "Scratch dir: $WORK"
echo "Wallet:      $WALLET"
echo

echo "── 1. Register the GPU provider (bound to the wallet) ──────────────────"
ai4science compute providers-add \
  --id demo-subgpu --wallet "$WALLET" --endpoint "$JOBS" --tier founder
echo

echo "── 2. Init a workspace + generate the CASSI scene ─────────────────────"
cd "$WORK"
ai4science init demo >/dev/null
cd demo
python code/generate_data.py --workspace .
# Use the SOTA-stand-in solver for a passing reconstruction.
cp "$HERE/run_solver.py" code/run_solver.py
echo

echo "── 3. AGENT SIDE: dispatch a reconstruction job ───────────────────────"
DISPATCH=$(ai4science compute dispatch --provider demo-subgpu \
            --benchmark L3-003-001-001-T1 \
            --run-command "python code/run_solver.py")
echo "$DISPATCH"
JOB_ID=$(echo "$DISPATCH" | grep -oE 'job [a-f0-9]{12}' | head -1 | awk '{print $2}')
echo

echo "── 4. GPU SIDE: run the poller once (executes the solver) ─────────────"
ai4science compute serve --provider demo-subgpu --once --allow-exec
echo

echo "── 5. AGENT SIDE: judge re-verifies → attribute credit ────────────────"
ai4science compute verify "$JOB_ID" --provider demo-subgpu
echo

echo "── 6. Credits per wallet (off-chain log) ──────────────────────────────"
ai4science compute credits
echo
echo "Done. Scratch dir (delete when finished): $WORK"
