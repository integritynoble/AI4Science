#!/usr/bin/env bash
# End-to-end **git-synced** AI4Science compute demo (Phase 0).
#
# Same loop as examples/compute_demo, but the CPU box (dispatcher) and the
# GPU box (provider) are SEPARATE git clones — the job request/ack/result
# JSON files flow between them over git via the `--git-sync` flag, exactly
# like the real CPU↔Windows-GPU setup. Everything runs on one machine using
# two clones of a throwaway bare repo, so it never touches a real remote.
#
#   bare repo + 2 clones (cpu, gpu)
#   → CPU: dispatch --git-sync           (pushes job_<id>.request.json)
#   → GPU: serve --once --git-sync       (pulls request, runs solver, pushes result)
#   → CPU: status/verify --git-sync      (pulls result, judge → credit)
#
# The 3 handshake files travel over git; the solve *workspace* (data + solver)
# is a shared dir — mirroring the design's "workspace reachable on the GPU box
# via shared/synced filesystem" assumption (git carries the small JSON, not the
# multi-GB data).
#
# Prereqs: `pip install -e .` with the venv active (so `ai4science` and
# `python` are on PATH), and `git`.
#
# Usage:
#   bash examples/gitsync_compute/run_demo.sh [WALLET_ADDRESS]
set -euo pipefail

WALLET="${1:-0xDe0000000000000000000000000000000000bEEF}"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

WORK="$(mktemp -d)"
export AI4SCIENCE_COMPUTE_REGISTRY="$WORK/registry.json"
INBOX_REL="inbox/compute_jobs"
CPU_INBOX="$WORK/cpu/$INBOX_REL"
GPU_INBOX="$WORK/gpu/$INBOX_REL"
echo "Scratch dir: $WORK"
echo "Wallet:      $WALLET"
echo

reg_cpu() { ai4science compute providers-add --id demo-subgpu --wallet "$WALLET" \
              --endpoint "$CPU_INBOX" --tier founder >/dev/null; }
reg_gpu() { ai4science compute providers-add --id demo-subgpu --wallet "$WALLET" \
              --endpoint "$GPU_INBOX" --tier founder >/dev/null; }

echo "── 1. Throwaway bare repo + two clones (the CPU box and the GPU box) ──"
git init -q --bare -b main "$WORK/origin.git"
git clone -q "$WORK/origin.git" "$WORK/cpu"
git clone -q "$WORK/origin.git" "$WORK/gpu"
for d in cpu gpu; do
  git -C "$WORK/$d" config user.email demo@pwm.local
  git -C "$WORK/$d" config user.name "pwm demo"
  git -C "$WORK/$d" checkout -q -B main
done
mkdir -p "$CPU_INBOX"; touch "$CPU_INBOX/.gitkeep"
git -C "$WORK/cpu" add "$INBOX_REL/.gitkeep"
git -C "$WORK/cpu" commit -q -m "seed compute_jobs inbox"
git -C "$WORK/cpu" push -q -u origin main
git -C "$WORK/gpu" pull -q origin main
git -C "$WORK/gpu" branch -q --set-upstream-to=origin/main main
echo "  CPU box clone: $WORK/cpu"
echo "  GPU box clone: $WORK/gpu  (shares origin: $WORK/origin.git)"
echo

echo "── 2. Build the solve workspace (data + SOTA-stand-in solver) ──"
# Shared workspace: git carries the JSON handshake; the workspace is reachable
# to both sides (here a shared dir; in production a synced/shared filesystem).
( cd "$WORK" && ai4science init ws >/dev/null )
WS="$WORK/ws"
( cd "$WS" && python code/generate_data.py --workspace . \
            && cp "$HERE/../compute_demo/run_solver.py" code/run_solver.py )
echo "  workspace: $WS"
echo

echo "── 3. CPU BOX: register provider (→ its clone's inbox) + dispatch --git-sync ──"
reg_cpu
DISPATCH=$(ai4science compute dispatch --provider demo-subgpu \
            --benchmark L3-003-001-001-T1 \
            --workspace "$WS" \
            --run-command "python code/run_solver.py" --git-sync)
echo "$DISPATCH"
JOB_ID=$(echo "$DISPATCH" | grep -oE 'job [a-f0-9]{12}' | head -1 | awk '{print $2}')
echo

echo "── 4. GPU BOX: register provider (→ its clone's inbox) + serve --once --git-sync ──"
# On two real machines each runs providers-add once; here we re-point the same
# registry entry to the GPU clone to simulate the second box.
reg_gpu
ai4science compute serve --provider demo-subgpu --once --allow-exec --git-sync
echo

echo "── 5. CPU BOX: pull the result + judge re-verifies → credit ──"
reg_cpu
ai4science compute status "$JOB_ID" --provider demo-subgpu --git-sync
ai4science compute verify "$JOB_ID" --provider demo-subgpu --workspace "$WS" --git-sync
echo

echo "── 6. Credits per wallet (off-chain log) ──"
ai4science compute credits --workspace "$WS"
echo
echo "Done. Scratch dir (delete when finished): $WORK"
