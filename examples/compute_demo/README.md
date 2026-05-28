# Compute-provider demo (Phase 0)

Replays the full AI4Science GPU-compute loop on a single machine:

```
register provider (wallet-bound) → init workspace → generate data
→ dispatch job → poller runs solver (GPU side) → judge verifies
→ verified-job credit lands on the wallet
```

It uses a throwaway registry + inbox (a `mktemp` dir) so it never touches
your real `~/.config/ai4science`.

## Run it

```bash
pip install -e .          # with your venv active
bash examples/compute_demo/run_demo.sh                 # demo wallet
bash examples/compute_demo/run_demo.sh 0xYourAddress…  # bind your own
```

## Expected tail

```
── 4. GPU SIDE: run the poller once (executes the solver) ──
▶ job <id> picked up
  ✓ job <id> ran → cert 0x…

── 5. AGENT SIDE: judge re-verifies → attribute credit ──
Judge decision: pass
Credit to 0x…: 1 verified-job credit(s)

── 6. Credits per wallet (off-chain log) ──
 0x…  │  1
```

## Files

| File | Role |
|---|---|
| `run_demo.sh` | the end-to-end loop (register → init → generate → dispatch → serve → verify → credits) |
| `run_solver.py` | a SOTA-grade GPU-solver **stand-in** (near-perfect reconstruction so the judge passes). Replace with your real solver on an actual GPU box. |

## What it proves

The deterministic Physics Judge re-verifies the returned reconstruction
independently (it recomputes the CASSI forward operator). A **pass**
earns one verified-job credit bound to the provider's wallet; a fake or
broken result earns **zero**. That's why untrusted GPU compute is safe —
providers are verified, not trusted.

To watch the agent drive this loop *conversationally* (dispatch → serve →
verify all as `⏺ Bash(...)` tool calls inside a chat), run
`ai4science chat` in a workspace and ask it to dispatch + verify a job.

See also:
- [`../../docs/COMPUTE_PROVIDERS_DESIGN.md`](../../docs/COMPUTE_PROVIDERS_DESIGN.md) — architecture + trust model + rollout phases
- [`../../docs/SUBGPU_SETUP_WINDOWS.md`](../../docs/SUBGPU_SETUP_WINDOWS.md) — set up a real Windows + CUDA GPU box
