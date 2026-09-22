# The evaluator outside the agent's world

An evaluator that shares the agent's process, working directory, tools, logs and network is an
evaluator an optimizer can improve its score against without improving its work. `ai4science/harness/
runtime/isolated_eval/` moves it out.

## The boundary

```
agent workspace                    evaluator root
  result.json                        store/            mode 0o000 at rest
  solver.py           handoff          seal.key        HMAC key, 0o600
       |             ---------->       handoff-<run>.json   sealed manifest
       |            hard link +        verdicts/<run>.json  sealed verdict
       |            sha256 each        incidents.jsonl      named crossings
       |                             work/             the child's cwd, HOME, TMPDIR
       |                             handoff/<run>/    read-only snapshot, 0o444
```

The child is `python -m ai4science.harness.runtime.isolated_eval.evaluator SPEC`, launched with:

- `cwd=` the evaluator's `work/`, never the agent's tree;
- `env=` built from nothing: `PATH=/usr/bin:/bin` (no agent tools), `HOME` and `TMPDIR` inside `work/`,
  `PYTHONHASHSEED=0`, and `PYTHONPATH` set to the installed package root — the agent's tree is never
  importable, and the launcher refuses outright if the evaluator's own code would come from it;
- `stdin=DEVNULL`, `close_fds=True` — no inherited handle on an agent log;
- no network: `deny_network()` replaces `socket.socket`, `create_connection`, `create_server`,
  `getaddrinfo` and `gethostbyname` *before any scorer is imported*.

`check_boundary()` then re-checks from inside the child and refuses to score if any of it did not take.

## Using it

```python
from ai4science.harness.runtime.isolated_eval import IsolatedEvaluator, IsolatedEvaluatorVerifier

evaluator = IsolatedEvaluator(
    root=Path("/var/lib/ai4science/evaluator"),      # not under the agent's workspace
    agent_workspace=workspace,
    criteria={"required_artifacts": ["result.json"]},
)
run_task(..., verifier=IsolatedEvaluatorVerifier(evaluator, run_id), ...)
```

It satisfies the same `Verifier` protocol as `CommandExitVerifier` and `ExternalEvaluatorVerifier`, so
it drops into `pev.run_task` unchanged. Unlike `ExternalEvaluatorVerifier` it needs no control plane to
be reachable: the boundary is a process and a store on this machine.

A custom scorer is `fn(handoff_root, criteria) -> {"decision", "score", "feedback"}` and must be a pure
function of the snapshot and the criteria. Keep deployment scorers on `scorer_path`, which may not be
inside the agent's tree either.

## Everything that can cross is named

`store.INCIDENT_KINDS` is the whole list. Each one lands in `incidents.jsonl` and in the verdict:

| kind | when |
|---|---|
| `artefact_edited_after_handoff` | a snapshot file's sha256 moved after the manifest was sealed |
| `artefact_added_after_handoff` / `artefact_removed_after_handoff` | the snapshot's file set moved |
| `manifest_edited_after_handoff` | the manifest no longer digests to its own recorded digest |
| `verdict_seal_broken` | a verdict's HMAC does not match, or it does not match the child's receipt |
| `verdict_missing` | a verdict was asked for and is not in the store |
| `network_attempt_refused` | a scorer reached for a socket |
| `boundary_violation` | the child found the agent's world reachable from inside it |
| `store_access_refused` | something reached for the store through `AgentVerdictView` |

A **tampered** run is `complete=False, repairable=False` — `blocked: unverifiable` in the loop, not a
replan. The optimizer does not get another go at a boundary it just tried to cross. A merely **failed**
run stays repairable.

Verdict payloads carry no timestamp, so the same run scored twice seals to the same digest. A diff
between two evaluations of one handoff means something moved.

## What the seal is, and is not

Two layers, because one is not enough:

1. **Refusal** — `chmod 0o000` on the store. The kernel denies an unprivileged process, including the
   owner. Real, and tested.
2. **Detection** — HMAC over a key inside the store. If layer 1 is undone anyway, reading the verdict
   raises `TamperDetected` with the incident named.

**Under a single uid, layer 1 is a refusal the agent's own uid can undo, and layer 2 is what catches
it.** Crossing the boundary is then *detected and named*, not prevented. Prevention needs the evaluator
to run as a different user or in a different mount namespace; `EvaluatorStore(..., owner_uid=...)` is
the hook for the first and is not yet exercised anywhere.

`deny_network()` is in-process monkeypatching, not a network namespace: it stops a scorer that reaches
for `socket`, not one that `ctypes`-calls `connect(2)` or spawns a subprocess. A scorer is the
evaluator's own code, so this is a guardrail against accident, not a sandbox.

Tests: `tests/runtime/test_isolated_evaluator.py`.
