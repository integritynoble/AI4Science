# AI4Science Compute Providers — Design

**Status:** Design (no code yet — approve before implementation)
**Date:** 2026-05-28
**Scope decision:** compute layer lives in the **AI4Science CLI** repo.
**Rollout decision:** **design doc first**, then MVP.

---

## 1. Problem

Today the AI4Science agent can *draft and edit* a solver, run the
deterministic Physics Judge, and validate schemas. What it **cannot** do
is *execute a real reconstruction* — especially for GPU-only solvers
(PnP-HDNet, DAUHST-9stg, RDLUF-MixS2, MST-L, ...). The contributor has to
leave the agent, run the solver by hand on a GPU box, and bring results
back.

We want to close that loop: the agent dispatches a solve to GPU compute,
results return, the judge verifies, and — eventually — the compute
provider earns PWM tokens for the work.

And we want this to scale beyond the founder: **special users provide
GPU**, bound to their wallet, earning rewards for verified work.

## 2. The key insight — why untrusted GPU is safe

A naïve compute marketplace has a trust problem: how do you know a
provider actually ran the solver and didn't just return a plausible-
looking `x_hat` (or a cached one, or noise)?

**PWM already solved this.** The deterministic Physics Judge re-verifies
every result independently:

- The provider returns `reconstruction_xhat.npy` + claimed metrics.
- The judge recomputes `A(x_hat)` with its **own** forward operator
  (`ai4science/judge/cassi/forward.py`) and the S1–S4 gates. It does not
  trust the provider's numbers.
- A provider **cannot fake a passing result**: garbage `x_hat` → S4
  forward-residual fails → no certificate → no reward.
- The judge runs on CPU, with **no LLM and no provider input** beyond the
  returned arrays. It is the source of truth.

**Consequence:** providers do not need to be trusted, only *verified*.
That is what makes a permissionless GPU market viable later — the same
mechanism that protects the founder's own runs protects against a
malicious community provider.

> This is the load-bearing property. Everything below assumes the judge
> stays deterministic, provider-independent, and LLM-free.

## 3. Architecture

```
ai4science agent (drafts / edits solver code)
        │   "run solver X on benchmark T1"
        ▼
┌──────────────────────────────────────────────┐
│ compute dispatch (AI4Science CLI)            │
│   - selects a provider from the registry     │
│   - packages the job (solver + benchmark ref)│
│   - writes a job request                     │
└──────────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────────┐
│ GPU provider registry (wallet-bound)         │
│   founder-1 sub-GPU server  (wallet 0x…1)    │  ← Phase 0: only this
│   (later) approved community GPUs (wallet 0x…N)
└──────────────────────────────────────────────┘
        │   provider runs solver on GPU
        ▼
   reconstruction_xhat.npy + claimed metrics + manifest
        │
        ▼
┌──────────────────────────────────────────────┐
│ deterministic Physics Judge                  │
│   recompute A(x_hat) vs y; S1–S4 gates       │
│   NO GPU, NO LLM, NO provider trust          │
└──────────────────────────────────────────────┘
        │
        ├─ pass → certificate_hash bound to provider wallet → PWM reward
        └─ fail → rejected, no reward, logged
```

The new box is **compute dispatch**. Everything downstream of the judge
(certificates, rewards, registry) is existing PWM platform territory and
is referenced, not rebuilt, here.

## 4. The provider registry

A provider is a record bound to a wallet. Proposed
`~/.config/ai4science/compute_providers.json` (or per-workspace
`.ai4science/compute_providers.json`):

```json
{
  "schema_version": "0.1",
  "providers": [
    {
      "provider_id": "founder-1-subgpu",
      "wallet_address": "0x________________________________________",
      "endpoint": {
        "kind": "file-inbox",
        "path": "pwm-team/coordination/agent-coord/inbox/compute_jobs/"
      },
      "gpu_capability": {
        "device": "CUDA 12.7",
        "frameworks": ["torch>=2.6"],
        "solver_classes": ["deep-unrolled", "transformer", "pnp"]
      },
      "status": "active",
      "trust_tier": "founder"
    }
  ]
}
```

- `wallet_address` is the binding. Verified rewards for jobs this provider
  completes accrue to this address. **The founder must supply the real
  address — this design will not fabricate one.**
- `trust_tier`: `founder` → `approved` → `open`. Affects nothing in the
  *verification* path (the judge treats all tiers identically); it only
  gates *who may register* and *job routing priority*.
- `endpoint.kind`: v1 reuses the existing file-inbox handshake (see §5).
  Later kinds: `http`, `modal`, `ssh`.

### Wallet binding — how a provider proves the address is theirs

For the founder's own server, trust is bootstrapped by the founder
editing the registry directly. For community providers later, binding
must be **proven**, not asserted:

- Provider signs a challenge nonce with the wallet's private key (SIWE —
  already used for platform login).
- The registry stores `wallet_address` + the signed proof.
- This prevents a provider from claiming rewards to a wallet they don't
  control.

v1 (founder-only) can defer SIWE proof; the founder editing their own
registry is the trust anchor. The schema reserves a `binding_proof`
field for when community registration opens.

## 5. Dispatch handshake (v1 reuses the file-inbox)

You already run a file-inbox handshake between the main CPU agent and the
sub-GPU server (`baseline_runs/CPU_GPU_SPLIT.md` with `[ACK]` blocks).
v1 dispatch reuses exactly that pattern — no new transport to build:

```
compute_jobs/
  job_<id>.request.json     ← agent writes: solver ref, benchmark id,
                               dataset ref, provider_id, max_runtime
  job_<id>.ack.json         ← sub-GPU writes: accepted, started_at
  job_<id>.result.json      ← sub-GPU writes: manifest (xhat path,
                               claimed metrics, certificate_hash,
                               provider wallet, status: testnet)
```

Job request schema (proposed):

```json
{
  "job_id": "uuid",
  "provider_id": "founder-1-subgpu",
  "solver": {"code_path": "code/", "run_command": "python code/run_solver.py"},
  "benchmark_id": "L3-003-001-001-T1",
  "dataset_ref": "gs://pwm-benchmark-datasets/.../standard_cassi_{00..09}.h5",
  "requested_at": "2026-05-28T…Z",
  "max_runtime_s": 3600
}
```

The result manifest is the **existing PR #12 schema** (`solution_id`,
`benchmark_id`, `solver_id`, `certificate_hash`, `omega_s`, `metrics`,
`gates {S1,S2,S3,S4}`, `reconstruction_artifacts`, `quality_ratio`,
`status: testnet`) **plus** a `provider` block:

```json
"provider": {
  "provider_id": "founder-1-subgpu",
  "wallet_address": "0x…1",
  "ran_at": "…", "wall_clock_s": 412, "device": "CUDA 12.7"
}
```

## 6. Reward attribution

1. Provider returns the result manifest with `certificate_hash` + wallet.
2. The judge **re-verifies** locally (the provider's gate numbers are
   advisory; the judge recomputes them).
3. If the judge passes, an attribution record links
   `certificate_hash → provider.wallet_address → reward_amount`.
4. v1: attribution is an **off-chain log** (`compute_attributions.jsonl`).
   On-chain settlement (PWM token transfer to the wallet) is a later
   phase, owned by the platform's onchain layer, gated by founders
   multisig — never auto-emitted by the CLI.

Reward sizing reuses your existing token economics (the "5% compute
markup"); the exact PWM-per-verified-job number is a governance decision,
not part of this design.

## 7. Security considerations

| Risk | Mitigation |
|---|---|
| Provider returns fake `x_hat` | Judge re-verifies independently → fail, no reward (§2) |
| Provider claims rewards to a wallet they don't own | SIWE-signed binding proof for community tier; founder bootstrap for Phase 0 |
| Malicious **solver code** runs on the provider's GPU | Provider sandboxes the job (container / Modal sandbox / restricted user). The provider chooses isolation; the protocol doesn't force untrusted code onto a host without it. |
| Provider exfiltrates a hidden test set | Hidden tests never leave the judge side; the provider only gets public benchmark inputs. Verification of hidden-test performance stays server-side. |
| Replay (resubmitting a past verified result) | `certificate_hash` is content-addressed over the submission; the registry rejects duplicate certificate hashes. |
| Wallet binding tampering | Registry edits for `founder`/`approved` tiers require founder sign-off; community self-registration requires the SIWE proof. |

## 8. Rollout phases

| Phase | Providers | Binding | Settlement |
|---|---|---|---|
| **0 (this step)** | founder-1 sub-GPU server only | founder edits registry (bootstrap trust) | off-chain attribution log |
| 1 | + a handful of approved users | SIWE-signed proof, founder approves | off-chain log, periodic manual payout |
| 2 | open registration | SIWE proof, automatic | on-chain PWM transfer on verified job (founders-multisig-gated contract) |

Phase 0 is deliberately small: prove the dispatch → run → judge → attribute
loop end-to-end with the founder's own GPU before any external compute or
real token flow.

## 9. What lives where

Per the scope decision (compute layer in the AI4Science CLI):

| Component | Home |
|---|---|
| `compute_providers.json` registry + loader | AI4Science CLI |
| `ai4science compute dispatch` command | AI4Science CLI |
| Job request/ack/result file handshake | AI4Science CLI (reuses inbox) |
| Judge re-verification | AI4Science CLI (already there) |
| Off-chain attribution log | AI4Science CLI (v1) |
| **On-chain reward settlement** | pwm_nonprofit platform (later; the CLI never moves tokens) |
| **Wallet SIWE proof verification** | platform (reuses existing SIWE login) |

The CLI dispatches and attributes; the **platform settles**. The CLI must
never hold keys or move tokens.

## 10. Proposed CLI surface (for the MVP, after approval)

```bash
ai4science compute providers                 # list registered providers
ai4science compute providers add \           # register a provider (founder)
    --id founder-1-subgpu --wallet 0x… \
    --endpoint file-inbox:<path> --tier founder
ai4science compute dispatch \                # send a job to a provider
    --solver code/ --benchmark L3-003-001-001-T1 \
    --provider founder-1-subgpu
ai4science compute status <job_id>           # poll the handshake
ai4science compute verify <job_id>           # run the judge on the result,
                                             # write the attribution record
```

## 11. Open questions (need answers before MVP)

1. **Founder-1 wallet address** — the real address to bind. (I will not
   fabricate this.)
2. **Inbox path** — is `pwm-team/coordination/agent-coord/inbox/` the
   right home for `compute_jobs/`, or should it be elsewhere?
3. **Does the sub-GPU server poll a path, or do we need a small watcher
   on its side?** v1 assumes it polls (as it does today for baseline_runs).
4. **Reward number** — PWM-per-verified-job, or defer entirely to a later
   governance decision and keep v1 attribution unit-less ("1 verified
   job" credits)?

## 12. Non-goals for v1

- No on-chain token movement from the CLI.
- No community/open provider registration (founder-only).
- No automatic solver-code sandboxing enforced by the protocol (the
  provider owns its isolation).
- No change to the deterministic judge's trust model.
