# Compute Mechanism — how a job goes from a user to a GPU and back

*How `ai4science compute` dispatches a request to a remote GPU provider, runs it,
verifies it, and accounts the PWM. Grounded in `ai4science/compute/` and verified
against live jobs (`3c8991c5653d`, `62825f38a368`) on 2026-06-15.*

> **TRANSPORT IS NOW HTTP (P4, 2026-06-15).** The git-synced inbox transport
> described in §3A below has been **removed**. Dispatch/claim/result and the
> workspace/reconstruction now flow through the **HTTP relay** on
> physicsworldmodel.org (`COMPUTE_HTTP_RELAY_DESIGN.md`) — any PWM-logged-in user,
> no pwm repo. The provider runs `ai4science compute serve --http`. §3A is kept
> for historical context only; `gitsync.py`/`dispatch.py` and `--git-sync` no
> longer exist.

Companion docs: `COMPUTE_HTTP_RELAY_DESIGN.md` (the live transport),
`COMPUTE_PROVIDERS_DESIGN.md` (design rationale),
`COMPUTE_PROVIDER_GUIDE.md` (how to run a provider).

---

## 1. Actors

| Role | Who | Command |
|---|---|---|
| **Dispatcher** | the user / main-CPU — has a job, holds PWM | `ai4science compute dispatch` |
| **Provider** | a GPU box (e.g. the founder sub-GPU) — earns PWM | `ai4science compute serve` |
| **Judge** | deterministic Physics verifier — **no LLM in the verdict path** | run automatically on the result |

The two machines never talk directly. They exchange a small set of JSON files
through a **shared inbox**.

---

## 2. The shared inbox

```
pwm-team/coordination/agent-coord/inbox/compute_jobs/     (inside the pwm git repo)
```

One job = three files with **distinct names**, so the two sides never git-conflict:

| File | Written by | Meaning |
|---|---|---|
| `job_<id>.request.json` | dispatcher | "please run this" |
| `job_<id>.ack.json`     | provider   | "I have claimed it" |
| `job_<id>.result.json`  | provider   | "here is the outcome" |

Liveness: the provider also stamps `heartbeat.<provider_id>.json` each pass
(published on a 60s throttle). The dispatcher reads it to show `● online` / `○ offline`;
offline = no heartbeat within 180s (`DEFAULT_STALE_AFTER_S`).

**State machine:** `requested` → `acked` → `completed`.

---

## 3. Transport — how the files cross machines

### (A) git-synced inbox — current; works for hosts that have the `pwm` repo

Because the inbox lives in the repo, **git is the transport**:

```
Dispatcher                       git (github.com/integritynoble/pwm)        Provider (GPU box)
  compute dispatch --git-sync                                                compute serve --git-sync
   write job_<id>.request.json                                                loop every 10s:
   git add/commit/push  ─────────►  job_<id>.request.json  ──pull──►           git pull --rebase --autostash
                                                                               write heartbeat (throttled push)
                                                                               run solver  (--allow-exec)
   git pull  ◄───────────  job_<id>.{ack,result}.json + results/  ◄─push──     git add/commit/push
   compute result <id>
```

Provider serve loop (`provider.py`), each pass:
1. `git pull --rebase --autostash` — fetch new `*.request.json`.
2. Stamp the heartbeat (local every pass; git-push throttled to 60s — `HB_PUSH_EVERY_S`).
3. For each pending request: write `.ack`, resolve workspace, run the solver, write
   `.result`, commit+push the ack + result (+ `ws/<job>/results/` when the workspace is
   under the repo).

> **`--git-sync` is mandatory on BOTH sides.** A `dispatch` without `--git-sync` writes the
> request only to the dispatcher's local inbox; it never reaches the repo, so the provider's
> `git pull` never sees it and the job stays `requested` forever. (This was the failure mode
> for the first MST-L dispatches — the git-synced GAP-TV probes landed and ran in ~5s.)

### (B) HTTP relay — Phase 2, not built yet

The git path requires the `pwm` repo, so it is effectively founder-to-founder. For an
**arbitrary user**, the plan (see `pwm-team/scripts/SUBGPU_SETUP.md`) is to route
dispatch/result through an authenticated HTTP endpoint on physicsworldmodel.org — reusing
the LLM proxy's existing auth + PWM-charge path — that the GPU box long-polls. That removes
the repo requirement and turns claim latency from a git round-trip into seconds.

---

## 4. The request, and how data actually moves

`request.json` (real, from job `3c8991c5653d`):

```json
{
  "job_id": "3c8991c5653d",
  "provider_id": "founder-1-subgpu",
  "wallet_address": "0xde81b29E...1A29",
  "workspace": "/home/spiritai/pwm/.../ws/cassi-gaptv-demo",      // dispatcher's local path
  "workspace_repo_relative": "pwm-team/.../ws/cassi-gaptv-demo",  // path relative to repo root
  "solver_code_path": "code/",
  "run_command": "python code/run_solver.py",
  "benchmark_id": "",
  "dataset_ref": "",
  "requested_at": "2026-06-15T12:29:33Z",
  "max_runtime_s": 600
}
```

Three classes of data, **each moved a different way** — this is the key design point:

| Data | How it travels | Notes |
|---|---|---|
| **Solver code + small inputs + model weights** | **via git** — committed inside the workspace under the repo | arrives on the GPU box with `git pull`. The 8.3 MB `mst_l.pth` goes here. |
| **Large datasets** | **NOT git** — request carries `dataset_ref` (e.g. a GCS URI); provider fetches directly | keeps the repo small. (MST-L `run_one.py` avoids this with a synthetic-scene fallback.) |
| **Results / reconstruction** | **back via git** — solver writes `results/reconstruction_xhat.npy`; serve loop commits `ws/<job>/results/` | only when the workspace is under the repo, so the dispatcher can re-verify independently. |

### Cross-machine workspace resolution

The dispatcher's absolute `workspace` (`/home/spiritai/...`) does not exist on the GPU box.
`_resolve_workspace(job, inbox)`:
- if the absolute `workspace` exists locally → use it (same-machine dispatch);
- else → join `workspace_repo_relative` onto **this** box's repo root (found from the inbox
  via `gitsync.find_repo_root`).

That is how a job authored on Linux runs against a Windows checkout. If the workspace is
neither present locally nor committed under the repo, the job runs with `solver_ran=false`.

---

## 5. Computation on the GPU

With `--allow-exec`, the provider runs the request's `run_command` as a subprocess **in the
resolved workspace directory**, bounded by `max_runtime_s`. The result captures:

```
solver_ran, solver_returncode, solver_error,
solver_stdout_tail, solver_stderr_tail,
provider.wall_clock_s, provider.device,
reconstruction_artifacts[]
```

> **Interpreter matters.** `run_command` must name an interpreter that has the solver's deps.
> On the founder Windows box, `C:/Python312/python.exe` has torch 2.6.0+cu124 + CUDA
> (GTX 1660 Ti); the poller's own venv has numpy but **no torch**. A torch solver dispatched
> with bare `python` dies with `ModuleNotFoundError: torch`. Use the full interpreter path.

---

## 6. Verification — integrity from recomputation, not trust

The provider's claimed metrics are **not** trusted. The deterministic Physics Judge
(`judge_cassi`, `attribution.py`) independently recomputes from the reconstruction artifact
and runs four gates:

- **S1** finite specifiability · **S2** Hadamard stability · **S3** approximability ·
  **S4** certifiability (forward residual ‖y−Φx̂‖, noise consistency, Fourier, spatial).
- `silent_failure` fires if S1+S3 pass but an S4 sub-check fails.

`final_decision == "pass"` → `credit = 1`; `needs_review` / `fail` → `credit = 0`. The judge
emits the `certificate_hash` carried in `result.json`. **No LLM ever touches this verdict.**

---

## 7. Payment — how PWM is calculated and settled

Pricing is provider-set natively in **PWM/hour** (`founder-1-subgpu` = 0.3 PWM/hr).
From `billing.py` / `attribution.py`:

```
pwm_owed = pwm_per_hour × wall_clock_seconds / 3600     # computed ONLY if the judge PASSES
```

- A failed/unverified job earns **nothing** (cost computed only when `credit == 1`).
- Each charge is split **90% to the provider, 10% to the PWM pool** (the canonical no-burn
  token design).
- An attribution record is appended to `~/.config/ai4science/compute_attributions.jsonl`
  (+ a per-workspace audit copy) with job id, wallet, judge decision, `wall_clock_s`, rate,
  and `pwm`. `ai4science compute credits` aggregates it.
- **Phase 0 (now): off-chain.** The CLI moves **no tokens** — it is an attribution ledger.
  The `PwmGate` is **off by default** (dev/CI), so it logs "would charge N PWM to <wallet>"
  rather than charging.
- **Phase 2: on-chain settlement is platform-owned.** The verified ledger becomes the basis
  for actual on-chain PWM flow; the CLI itself never holds keys or transfers tokens.

The wallet in "PWM is charged to `0x…`" is the **provider's earning wallet** — the account
that accrues the compute reward on a verified pass.

---

## 8. End-to-end summary

```
dispatch (git push request)
   → provider git pull + write ack
      → run solver in the resolved workspace (--allow-exec)
         → Judge recomputes + certifies (S1–S4)
            → result + reconstruction pushed back
               → PWM attributed 90/10  — only on a verified pass
```

## 9. Quick reference

```bash
# Dispatcher (must use --git-sync; workspace committed under the pwm repo):
ai4science compute dispatch -p founder-1-subgpu \
  -w <workspace-under-pwm-repo> \
  --run-command "C:/Python312/python.exe run_one.py" \
  --git-sync

ai4science compute status <job_id> --git-sync      # poll requested/acked/completed
ai4science compute providers                        # ● online / ○ offline + PWM/hr
ai4science compute credits                          # aggregated attribution ledger

# Provider (the GPU box):
ai4science compute serve --provider founder-1-subgpu --allow-exec --git-sync --interval 10
```
