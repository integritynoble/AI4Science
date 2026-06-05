# Computational-Imaging Domain Agent (Design Spec)

**Date:** 2026-06-06
**Status:** Approved for planning
**Relationship:** Builds on the agent framework (`2026-06-04-agent-framework-design.md`). Establishes the **reusable pattern for `specific` domain agents** and ships **computational-imaging** as the first exemplar. Cost/charging is deferred to a shared PWM-economics spec (the same one that will implement paper-review charging).

---

## 1. Overview

A `specific` domain agent in the framework is just two pieces:

1. An **`AgentSpec`** file under `ai4science/harness/agents/specs/` — `tier="science"`,
   `category="specific"`, a rich **domain-expert system prompt**, and a list of
   capability bundles.
2. A **domain capability bundle** registered in
   `ai4science/harness/agents/capabilities.py` — the domain's first-class tools.

Future domains (biology, chemistry, …) follow the same shape: add a spec + a
bundle. This spec builds **computational-imaging** as the exemplar:

- **Enriched expert prompt** (CASSI / snapshot compressive spectral imaging).
- A new **`computational-imaging` capability bundle** (`cassi_tools.py`) with three
  tools: `cassi_forward_check` (local physics sanity check), `cassi_dispatch`
  (run a solver on a remote GPU — cost-guarded), `cassi_result` (poll + judge →
  PSNR/score_q).

**Cost model (the economic shape, charging deferred):**
- **Compute provider** = the wallet/server hosting the GPU (currently the sub-GPU
  server). This is the `provider` in dispatch — infrastructure.
- **Solution provider** = the author of a *registered solution*. **They define the
  PWM cost** of running their solution.
- **User** pays the *solution-provider-defined* PWM to run a solution on the GPU;
  the compute provider is settled separately for the hardware.
- In **this** spec, `cassi_dispatch` only **previews** the cost (a stub) and
  requires `confirm=True` to dispatch the compute job. **No PWM moves here.** The
  real price lookup + debit + routing land in the PWM-economics spec.

---

## 2. Components & Files

### 2.1 `ai4science/harness/agents/specs/computational_imaging.py` (enriched)
Replace the thin prompt with a real CASSI/spectral-imaging expert prompt covering:
the forward model `y = Φx` (coded aperture + dispersion); classical solvers
(GAP-TV, ADMM/TwIST, DeSCI) and deep solvers (unrolled networks — MST, MST-L,
DAUHST); the registered benchmarks (e.g. `L3-003`) and metrics (PSNR, SSIM, the
registry `score_q`); the physics-judge stages S1–S4 (forward residual, Fourier/
noise/spatial consistency); and a workflow steer: ground in `pwm_solutions`
baselines, sanity-check reconstructions with `cassi_forward_check`, then evaluate
on GPU via `cassi_dispatch`/`cassi_result`. Capabilities:
`("pwm-actions", "pwm-data", "computational-imaging")`.

### 2.2 `ai4science/harness/cassi_tools.py` (new)
`cassi_tools() -> list[Tool]` returning the three tools below. All tools:
`mutating=False`; errors return `"[cassi error] ..."`; file-path args are
workspace-contained (reject `..`/absolute escapes, mirroring `paper_tools._contained`).

**Tool 1 — `cassi_forward_check`** (local, no GPU)
- `parameters`: `recon` (str, required), `mask` (str, required), `measurement`
  (str, required) — paths to `.npy` arrays in the workspace.
- `func(workspace, *, recon, mask, measurement)`: load the three arrays with
  `numpy.load` (workspace-contained); `y_hat = cassi_forward(x, mask)`
  (from `ai4science.judge.cassi.forward`); compute relative residual
  `r = ||y_hat - y|| / (||y|| + 1e-12)`; return a line with `r` and a hint
  (`r < 0.05` → "consistent"; `< 0.2` → "marginal"; else "inconsistent").
- Errors: missing/unreadable file, shape mismatch → `[cassi error] ...`.

**Tool 2 — `cassi_dispatch`** (remote GPU, cost-guarded)
- `parameters`: `solver` (str, default `"code/"` — path to solver code in the
  workspace), `benchmark` (str, required — e.g. `"L3-003-001-001-T1"`),
  `provider` (str, default `""` — compute provider id; empty → first configured),
  `solution_ref` (str, default `""` — a registered solution id, if running one),
  `confirm` (bool, default `False`).
- `func(workspace, *, solver="code/", benchmark, provider="", solution_ref="", confirm=False)`:
  1. Resolve the compute provider: `get_provider(provider)` if given, else the
     first provider in the registry (`_default_provider()`); none → `[cassi error]
     no compute provider configured (ai4science compute providers add ...)`.
  2. `cost, sol_provider = _solution_cost(solution_ref)` (the stub seam, §2.4).
  3. Workspace-contain `solver`.
  4. If **not** `confirm`: return a **preview** (no dispatch) listing compute
     provider id + endpoint, benchmark, solver path, solution
     (`solution_ref or "your own solver code"`), and the cost line
     (`PWM cost: {cost} (set by the solution provider {sol_provider}); GPU by
     compute provider {provider_id}`), ending with
     `Pass confirm=true to dispatch.`
  5. If `confirm`: `job = dispatch_job(provider=prov, workspace=ws,
     benchmark_id=benchmark, solver_code_path=solver)`; return the `job_id`,
     the inbox request path, the cost note, and "poll with cassi_result(job_id=...)".
- **No PWM is debited here** — the cost is informational; real charging is deferred.

**Tool 3 — `cassi_result`** (poll + judge)
- `parameters`: `job_id` (str, required), `provider` (str, default `""`).
- `func(workspace, *, job_id, provider="")`: resolve provider (as above);
  `st = job_state(provider.endpoint_path, job_id)`; if `st["state"] != "done"`,
  return the state (e.g. `pending`/`accepted`/`running`/`error`). If done:
  `res = read_result(endpoint_path, job_id)`; judge the result workspace via
  `judge_cassi(submission=<result workspace>, benchmark=...)`; return a summary:
  judge `status`/`final`, PSNR, `score_q` (pulled from the judge report/result),
  and the result path. Unknown job / missing result → `[cassi error] ...`.

### 2.3 `ai4science/harness/agents/capabilities.py` (modify)
Add a provider + register it:
```python
def _computational_imaging(ctx):
    from ai4science.harness.cassi_tools import cassi_tools
    return list(cassi_tools())
# in CAPABILITY_BUNDLES:
    "computational-imaging": _computational_imaging,
```

### 2.4 Cost seam — `_solution_cost` (in `cassi_tools.py`)
```python
def _solution_cost(solution_ref: str):
    """STUB economics seam. Returns (cost_str, solution_provider).

    The PWM cost of running a solution is DEFINED BY THE SOLUTION PROVIDER (the
    registered solution's author), NOT the compute provider. The PWM-economics
    spec replaces this with a real registry/on-chain price lookup + a user debit
    routed to the solution provider (compute provider settled separately)."""
    if not solution_ref:
        return ("none (your own solver — compute settled in the economics layer)",
                "you")
    return ("(set by the solution provider — deferred to the economics layer)",
            f"of {solution_ref}")
```
No token movement in this spec; `cassi_dispatch` only previews this.

---

## 3. Data Flow

```
/mode specific imaging  → computational-imaging agent
  agent grounds in pwm_solutions (best registered CASSI solutions/scores)
  agent writes a solver under  code/  in the workspace
  cassi_forward_check(recon=..., mask=..., measurement=...)   # local sanity, no GPU
  cassi_dispatch(solver="code/", benchmark="L3-003-...-T1")   # confirm=False → PREVIEW + cost
     → agent shows the user the cost; user/agent re-calls with confirm=true
  cassi_dispatch(..., confirm=true)  → dispatch_job → job_id
  cassi_result(job_id=...)  → pending → ... → done → judge → PSNR / score_q
```

---

## 4. Error Handling

| Failure | Behavior |
|---|---|
| `cassi_forward_check`: missing/unreadable `.npy`, shape mismatch | `[cassi error] ...` |
| Any file path escapes the workspace (`..`/absolute) | `[cassi error] path escapes the workspace: ...` |
| `cassi_dispatch`: no compute provider configured | `[cassi error] no compute provider configured ...` |
| `cassi_dispatch` without `confirm` | preview (no dispatch, no spend) |
| `cassi_result`: unknown job / no result file | `[cassi error] ...` |
| `cassi_result`: job not done | return the current state string |
| `judge_cassi` raises | `[cassi error] judge failed: ...` |

---

## 5. Testing (TDD)

- **`cassi_forward_check`:** synthetic small arrays — build `x`, `mask`, set
  `y = cassi_forward(x, mask)` → residual ≈ 0 ("consistent"); a perturbed `y`
  → residual > 0. Path-escape (`../x.npy`) → `[cassi error]`. (numpy 2.4 is
  available locally.)
- **`cassi_dispatch`:** monkeypatch `cassi_tools.get_provider` (and
  `_default_provider`) to a fake provider with an `endpoint_path`, and
  `cassi_tools.dispatch_job` to return a fake job. Assert: `confirm=False` returns
  a preview containing the cost line AND does NOT call `dispatch_job`;
  `confirm=True` calls `dispatch_job` and returns the `job_id`; no provider →
  `[cassi error]`. `mutating is False`.
- **`cassi_result`:** monkeypatch `job_state` (pending → returns state without
  judging; done → `read_result` + `judge_cassi` mocked → returns a summary with
  PSNR/score_q). Unknown job → `[cassi error]`.
- **`_solution_cost`:** empty ref → "your own solver" tuple; non-empty ref →
  "set by the solution provider" tuple naming the ref.
- **Integration:** `capabilities.CAPABILITY_BUNDLES` has `"computational-imaging"`;
  `resolve_capability("computational-imaging", ctx)` returns the 3 `cassi_*` tools;
  the `computational-imaging` spec lists the bundle; `build_registry_for` for the
  agent includes `cassi_forward_check`/`cassi_dispatch`/`cassi_result`; **common
  does NOT** (moat). Framework moat/dispatch tests still pass.
- **Live E2E (controller):** `/mode specific imaging` resolves the agent;
  `cassi_forward_check` on a real synthetic `.npy` pair (local, real); a
  `cassi_dispatch` **preview** (confirm omitted → no spend, no real GPU).

---

## 6. Reusable domain-agent pattern (documented outcome)

After this spec, adding a domain agent is: (1) drop `specs/<domain>.py` with an
expert prompt + `capabilities`; (2) optionally add a `<domain>` capability bundle
in `capabilities.py` wrapping that domain's tools. computational-imaging is the
worked example; biology/chemistry reuse the shape. This will be captured in
`docs/CLAUDE_CODE_PARITY.md` (a "Specific domain agents" note) so the next domain
is a copy-paste-and-edit.

---

## 7. Out of Scope (future / deferred)

- **PWM-economics layer:** the real solution-price lookup, the user PWM debit, and
  routing to the solution provider / settling the compute provider. Here it is
  only the `_solution_cost` stub + a cost preview. (Shared spec with paper-review
  charging.)
- **Actual GPU runs in CI/tests:** dispatch/result are unit-tested with mocks; a
  real GPU job stays manual/optional (env-dependent provider).
- **New reconstruction algorithms:** the agent writes solvers; we provide the
  eval loop, not the solvers.
- **Permission-gate integration for paid actions:** the harness gate keys on
  `write/edit/bash` by name; rather than change it, `cassi_dispatch` self-guards
  with `confirm=True`.
