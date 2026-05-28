# Git-synced compute demo (Phase 0)

Replays the full AI4Science GPU-compute loop with the **dispatcher and the
provider on separate git clones** — the job handshake travels over `git`
via the `--git-sync` flag, exactly like the real CPU↔Windows-GPU setup:

```
bare repo + 2 clones (cpu, gpu)
→ CPU: dispatch --git-sync        (pushes job_<id>.request.json)
→ GPU: serve --once --git-sync    (pulls request, runs solver, pushes result)
→ CPU: status/verify --git-sync   (pulls result, judge → credit)
```

Everything runs on one machine using two clones of a throwaway bare repo
and a `mktemp` registry, so it never touches a real remote or your
`~/.config/ai4science`. For the single-machine, in-process version (no git),
see [`../compute_demo`](../compute_demo).

## Run it

```bash
pip install -e .          # with your venv active (so `ai4science` + `python` are on PATH)
bash examples/gitsync_compute/run_demo.sh                 # demo wallet
bash examples/gitsync_compute/run_demo.sh 0xYourAddress…  # bind your own
```

## Expected tail

```
── 4. GPU BOX: register provider (→ its clone's inbox) + serve --once --git-sync ──
  inbox:   …/gpu/inbox/compute_jobs  (git-synced)
▶ job <id> picked up
  ✓ job <id> ran → cert 0x…
  ↥ pushed result for <id>

── 5. CPU BOX: pull the result + judge re-verifies → credit ──
Job <id> — state: completed
Judge decision: pass
Credit to 0x…: 1 verified-job credit(s)

── 6. Credits per wallet (off-chain log) ──
 0x…  │  1
```

## What it proves

- **The git handshake works both directions.** The CPU clone commits+pushes
  the request; the GPU clone pulls it, runs the solver, and commits+pushes the
  `ack`+`result`; the CPU clone pulls the result back. The three filenames are
  distinct (`.request` / `.ack` / `.result`), so the two sides never collide.
- **Git carries the small JSON, not the data.** The solve *workspace* (data +
  solver, multi-GB in production) is a shared/synced path — only the handshake
  manifests go over git. This mirrors the design's "workspace reachable on the
  GPU box via shared/synced filesystem" assumption.
- **Verified, not trusted.** The deterministic Physics Judge re-verifies the
  returned reconstruction independently after the git round-trip. A **pass**
  earns one credit bound to the provider's wallet; a fake/broken result earns
  **zero**.

To watch an agent drive this conversationally (each `compute …` step as a
`⏺ Bash(...)` tool call), run `ai4science chat` and ask it to dispatch a
git-synced job.

## Files

| File | Role |
|---|---|
| `run_demo.sh` | the end-to-end git-synced loop across two clones |
| (solver) | reuses [`../compute_demo/run_solver.py`](../compute_demo/run_solver.py), a SOTA-grade stand-in so the judge passes |

See also:
- [`../../docs/COMPUTE_PROVIDERS_DESIGN.md`](../../docs/COMPUTE_PROVIDERS_DESIGN.md) — architecture + trust model
- [`../../docs/SUBGPU_SETUP_WINDOWS.md`](../../docs/SUBGPU_SETUP_WINDOWS.md) — real Windows + CUDA GPU box with `--git-sync`
