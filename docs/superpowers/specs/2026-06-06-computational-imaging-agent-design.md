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
- A new **`computational-imaging` capability bundle** (`cassi_tools.py`) with four
  tools: `cassi_solutions` (list ALL registered imaging solutions across **mainnet
  and testnet**, each marked by chain), `cassi_forward_check` (local physics sanity
  check), `cassi_dispatch` (run a solver on the sub-GPU server — cost-guarded),
  `cassi_result` (poll + judge → PSNR/score_q).

**All solutions, both chains, marked.** The CI agent must surface the full set of
registered imaging solutions from **both mainnet and testnet**, each tagged with
its chain. The explorer leaderboard does not currently carry a per-solution chain
field, so `cassi_solutions` aggregates from two chain-scoped explorer bases (see
§2.5) and labels each entry `chain="mainnet"|"testnet"`.

**Cost model (the economic shape, charging deferred):**
- **Compute provider** = the wallet/server hosting the GPU (currently the **sub-GPU
  server**). This is the `provider` in dispatch — infrastructure.
- **Solution provider** = the author of a *registered solution*. **They define the
  PWM cost** of running their solution, and the user's PWM payment is routed to the
  solution provider's address. For the **genesis CASSI solutions** the solution
  provider is the **third founder address
  `0xde81b29E42F95C92c9A4Dc78882d0F05D2C81A29`** — that is where users' PWM for
  using these solutions is paid.
- **User** pays the *solution-provider-defined* PWM (to the solution provider /
  third-founder address) to run a solution on the GPU; the compute provider (sub-GPU
  server) is settled separately for the hardware.
- In **this** spec, `cassi_dispatch` only **previews** the cost AND the recipient
  address (a stub), and requires `confirm=True` to dispatch the compute job. **No
  PWM moves here.** The real price lookup + debit + routing land in the
  PWM-economics spec.

---

## 2. Components & Files

### 2.1 `ai4science/harness/agents/specs/computational_imaging.py` (enriched)
Replace the thin prompt with a real CASSI/spectral-imaging expert prompt covering:
the forward model `y = Φx` (coded aperture + dispersion); classical solvers
(GAP-TV, ADMM/TwIST, DeSCI) and deep solvers (unrolled networks — MST, MST-L,
DAUHST); the registered benchmarks (e.g. `L3-003`) and metrics (PSNR, SSIM, the
registry `score_q`); the physics-judge stages S1–S4 (forward residual, Fourier/
noise/spatial consistency); and a workflow steer: survey ALL registered solutions
across mainnet+testnet with `cassi_solutions` (note which are mainnet vs testnet),
ground in the best baselines, sanity-check reconstructions with `cassi_forward_check`,
then evaluate on the sub-GPU server via `cassi_dispatch` (cost is paid in PWM to the
solution provider — preview it, confirm to spend) / `cassi_result`. Capabilities:
`("pwm-actions", "pwm-data", "computational-imaging")`.

### 2.2 `ai4science/harness/cassi_tools.py` (new)
`cassi_tools() -> list[Tool]` returning the four tools below. All tools:
`mutating=False`; errors return `"[cassi error] ..."`; file-path args are
workspace-contained (reject `..`/absolute escapes, mirroring `paper_tools._contained`).

**Tool 1 — `cassi_solutions`** (all registered imaging solutions, both chains)
- `parameters`: `benchmark` (str, default `""` — a specific benchmark id; empty →
  all imaging benchmarks).
- `func(workspace, *, benchmark="")`: via `cassi_solutions_multichain` (§2.5),
  query both the **mainnet** and **testnet** explorer bases for the imaging
  benchmark leaderboards, flatten the registered solutions, and tag each entry
  `chain="mainnet"|"testnet"`. Return a compact, grouped listing — e.g.
  `[mainnet] L3-003 MST-L score_q 0.95 (PSNR 35.3)` / `[testnet] ...` — with a
  trailing note if a chain's base is not configured/unreachable
  (`mainnet: not configured` rather than silently dropping it). JSON-dumped detail
  truncated to ~20k like the research tools.
- This is the "contain ALL testnet and mainnet solutions, marked" requirement.

**Tool 2 — `cassi_forward_check`** (local, no GPU)
- `parameters`: `recon` (str, required), `mask` (str, required), `measurement`
  (str, required) — paths to `.npy` arrays in the workspace.
- `func(workspace, *, recon, mask, measurement)`: load the three arrays with
  `numpy.load` (workspace-contained); `y_hat = cassi_forward(x, mask)`
  (from `ai4science.judge.cassi.forward`); compute relative residual
  `r = ||y_hat - y|| / (||y|| + 1e-12)`; return a line with `r` and a hint
  (`r < 0.05` → "consistent"; `< 0.2` → "marginal"; else "inconsistent").
- Errors: missing/unreadable file, shape mismatch → `[cassi error] ...`.

**Tool 3 — `cassi_dispatch`** (sub-GPU server, cost-guarded)
- `parameters`: `solver` (str, default `"code/"` — path to solver code in the
  workspace), `benchmark` (str, required — e.g. `"L3-003-001-001-T1"`),
  `provider` (str, default `""` — compute provider id; empty → first configured),
  `solution_ref` (str, default `""` — a registered solution id, if running one),
  `confirm` (bool, default `False`).
- `func(workspace, *, solver="code/", benchmark, provider="", solution_ref="", confirm=False)`:
  1. Resolve the compute provider: `get_provider(provider)` if given, else the
     first provider in the registry (`_default_provider()`); none → `[cassi error]
     no compute provider configured (ai4science compute providers add ...)`.
  2. `cost, recipient, sol_provider = _solution_cost(solution_ref)` (the stub seam,
     §2.4) — `recipient` is the third-founder address for genesis CASSI solutions.
  3. Workspace-contain `solver`.
  4. If **not** `confirm`: return a **preview** (no dispatch) listing compute
     provider id + endpoint (the sub-GPU server), benchmark, solver path, solution
     (`solution_ref or "your own solver code"`), and the cost line
     (`PWM cost: {cost} — pay to {recipient} (solution provider {sol_provider}); GPU by
     compute provider {provider_id}`), ending with `Pass confirm=true to dispatch.`
  5. If `confirm`: `job = dispatch_job(provider=prov, workspace=ws,
     benchmark_id=benchmark, solver_code_path=solver)`; return the `job_id`,
     the inbox request path, the cost note, and "poll with cassi_result(job_id=...)".
- **No PWM is debited here** — the cost is informational; real charging is deferred.

**Tool 4 — `cassi_result`** (poll + judge)
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
# Genesis CASSI solutions are authored by the third founder; users' PWM for using
# them is paid to this address. (Per-solution recipients become dynamic once the
# economics layer reads each solution's provider from the registry.)
GENESIS_SOLUTION_PROVIDER = "0xde81b29E42F95C92c9A4Dc78882d0F05D2C81A29"


def _solution_cost(solution_ref: str):
    """STUB economics seam. Returns (cost_str, recipient_addr, solution_provider).

    The PWM cost of running a solution is DEFINED BY THE SOLUTION PROVIDER (the
    registered solution's author), NOT the compute provider, and the user's PWM is
    paid to the solution provider's address. The PWM-economics spec replaces this
    with a real registry/on-chain price lookup + a user debit routed to that
    address (compute provider settled separately)."""
    if not solution_ref:
        return ("none (your own solver — compute settled in the economics layer)",
                "you", "you")
    return ("(set by the solution provider — deferred to the economics layer)",
            GENESIS_SOLUTION_PROVIDER, f"of {solution_ref}")
```
No token movement in this spec; `cassi_dispatch` only previews cost + recipient.

### 2.5 Multi-chain solution source — `cassi_solutions_multichain` (in `cassi_tools.py`)
The explorer leaderboard carries no per-solution chain field and `pwm_data.base()`
is a single endpoint. To surface mainnet **and** testnet solutions marked by chain:
```python
def _chain_bases():
    """(label, base_url) for each configured chain. Mainnet may be unset."""
    import os
    out = []
    mn = os.environ.get("PWM_EXPLORER_BASE_MAINNET", "")
    tn = os.environ.get("PWM_EXPLORER_BASE_TESTNET",
                        os.environ.get("PWM_EXPLORER_BASE",
                                       "https://explorer.physicsworldmodel.org/api"))
    if mn:
        out.append(("mainnet", mn.rstrip("/")))
    out.append(("testnet", tn.rstrip("/")))
    return out, bool(mn)
```
`cassi_solutions_multichain(benchmark="")` iterates `_chain_bases()`; for each, pulls
the imaging benchmark leaderboard(s) via the explorer (reusing `transport.get_json`
+ the `pwm_data.solutions` flattening shape), tags every entry with its `chain`
label, and aggregates. When `benchmark` is empty it iterates the imaging benchmarks
(those whose id matches the CASSI/L3 imaging set — e.g. id starts with the imaging
benchmark prefix, or `category`/`title` matches "imaging"/"CASSI"). If the mainnet
base is unset, results carry only testnet entries plus a `mainnet: not configured`
note (no silent drop). Network failure on one chain → that chain reports
`unavailable`, the other still returns. This keeps the agent forward-compatible:
once a mainnet indexer URL is set via `PWM_EXPLORER_BASE_MAINNET`, mainnet solutions
appear automatically, marked.

---

## 3. Data Flow

```
/mode specific imaging  → computational-imaging agent
  cassi_solutions()  → ALL registered imaging solutions, marked [mainnet]/[testnet]
  agent grounds in the best registered CASSI solutions/scores across both chains
  agent writes a solver under  code/  in the workspace
  cassi_forward_check(recon=..., mask=..., measurement=...)   # local sanity, no GPU
  cassi_dispatch(solver="code/", benchmark="L3-003-...-T1")   # confirm=False → PREVIEW:
     cost + recipient (third-founder 0xde81…1A29) + sub-GPU compute provider
     → agent shows the user the cost; user/agent re-calls with confirm=true
  cassi_dispatch(..., confirm=true)  → dispatch_job (sub-GPU server) → job_id
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

- **`cassi_solutions` / `cassi_solutions_multichain`:** monkeypatch `transport.get_json`
  (or the leaderboard fetch) to return canned solutions for a testnet base and a
  mainnet base. With `PWM_EXPLORER_BASE_MAINNET` set → entries from both chains, each
  tagged `chain="mainnet"`/`"testnet"`; with it unset → testnet entries + a
  `mainnet: not configured` note. One chain raising → that chain `unavailable`, the
  other still returned. The output string marks each solution's chain.
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
- **`_solution_cost`:** empty ref → 3-tuple `(..., "you", "you")`; non-empty ref →
  3-tuple whose **recipient is `GENESIS_SOLUTION_PROVIDER` (0xde81…1A29)** and whose
  provider names the ref. `cassi_dispatch` preview string includes that recipient.
- **Integration:** `capabilities.CAPABILITY_BUNDLES` has `"computational-imaging"`;
  `resolve_capability("computational-imaging", ctx)` returns the 4 `cassi_*` tools;
  the `computational-imaging` spec lists the bundle; `build_registry_for` for the
  agent includes `cassi_solutions`/`cassi_forward_check`/`cassi_dispatch`/`cassi_result`;
  **common does NOT** (moat). Framework moat/dispatch tests still pass.
- **Live E2E (controller):** `/mode specific imaging` resolves the agent;
  `cassi_solutions` returns the registered imaging solutions marked by chain (live
  explorer, testnet today); `cassi_forward_check` on a real synthetic `.npy` pair
  (local, real); a `cassi_dispatch` **preview** showing the third-founder recipient
  (confirm omitted → no spend, no real GPU).

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
