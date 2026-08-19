# Progress

Amendment 61 work, newest round last within each task. Line references in this
file were re-checked against the working tree on 2026-08-18; if you are reading
it after further edits, trust `grep`, not this file.

## Amendment 61 Task 2 — response-metadata transport

The contract under test is documented at `ai4science/harness/adapters/base.py:15-27`:
**exactly one `ResponseMeta` per provider request, emitted before any semantic
event, carrying response-derived observations only.** A requested value must
never be copied into an observed field, and a missing/unprovable route must
visibly hold with zero fallback.

### Round 1 — three negative fixtures (recorded 2026-08-17, 3 passed)

- `test_openai_stream_keeps_absent_provider_observations_none`: a requested model plus a provider chunk with no response metadata leaves `observed_model`, `system_fingerprint`, and `response_id` as `None`.
- `test_openai_compat_chat_with_meta_does_not_invent_observations`: a non-streaming provider response with no metadata fields leaves all provider observations as `None`.
- `test_proxy_cannot_invent_missing_provider_observations`: proxy round-trip and transport rewriting preserve absent observations as `None`; only `transport` becomes `proxy`.

Round 1 was **REJECTED** by independent review (`.superpowers/sdd/implementation-plan/task-2-review.md`,
verdict FAIL/FAIL). The three fixtures above are correct but only cover happy-shaped
streams; they did not instrument the contract boundaries, so a first-chunk-only
implementation passed them while losing metadata, emitting zero metadata, or
emitting more than one.

### Round 2 (fix round) — eleven further negative instruments plus one positive

Direct stream (`tests/test_response_metadata.py`):

- `test_openai_stream_collects_metadata_from_nonsemantic_prelude` — metadata arriving after an empty `{"choices": []}` prelude is not lost.
- `test_openai_stream_combines_partial_metadata_before_first_semantic_event` — `id`, `model`, and `system_fingerprint` split across three prelude chunks are all captured, first-writer-wins.
- `test_openai_empty_stream_emits_one_none_observation_meta` — a stream that closes with no chunk still yields exactly one all-`None` meta.
- `test_openai_pre_first_chunk_exception_exposes_meta_then_original_failure` — an iterator raising before its first yield yields the meta, then the original exception unchanged.
- `test_openai_stream_create_failure_exposes_meta_then_original_failure` — the same for a failure inside `transport.sse_post`.

Proxy and gateway (`tests/test_llm_proxy.py`):

- `test_proxy_duplicate_metadata_yields_one_then_fails_closed`
- `test_proxy_text_before_metadata_exposes_none_meta_then_fails_closed`
- `test_proxy_malformed_metadata_exposes_none_meta_then_fails_closed`
- `test_proxy_empty_stream_exposes_none_meta_then_fails_closed`
- `test_gateway_pre_meta_failure_emits_none_meta_before_error_semantics`
- `test_gateway_empty_adapter_emits_none_meta_before_bill`
- `test_proxy_clean_termination_after_valid_metadata_is_accepted` (positive control: the fail-closed guards do not reject a well-formed stream)

Round 2 review verdict: **SPEC COMPLIANCE PASS, CODE QUALITY FIX** — the transport
state machine was accepted; five further code-quality findings were raised.

### Round 3 (fix round) — the canonical Amendment 61 hold

Finding NEW-1: the missing-credential precondition `raise` sat in the `stream()`
generator body, *outside* the `_parse_stream` sequencing. On the canonical
Amendment 61 case (backend `pwm_qwen`, no credential, `PWM_NO_PROXY=1`) the
observed result was `seq=[] metas=0 raised=RuntimeError`. That is a genuine hard
hold — nothing continues on another model, so zero-fallback was never breached —
but it emitted no `ResponseMeta`, so a downstream strict guard that decides
held-vs-proven by inspecting the emitted metadata sees nothing and must
special-case the exception.

Two instruments added, **written and observed RED before the production change**:

- `test_openai_missing_credential_emits_none_observation_meta_then_holds` — drives the real `factory.adapter_for("pwm_qwen")` path with `PWM_NO_PROXY=1` and `resolve_key -> None`; asserts the event sequence is exactly one all-`None` `ResponseMeta` and that the original `RuntimeError` type and message survive verbatim.
- `test_openai_missing_credential_meta_holds_with_no_creds_object` — the same hold with no `CredInfo` at all, so the fix cannot degrade into an `AttributeError`.

RED (pre-fix): `2 failed, 10 deselected` — `assert [] == [ResponseMeta(...)]`.
GREEN (post-fix): `2 passed, 10 deselected`.

Post-fix probe of the real canonical path:

```text
seq= [ResponseMeta(backend='pwm_qwen', requested_model='qwen3.8:27b', observed_model=None,
                   system_fingerprint=None, response_id=None, transport='direct')]
metas= 1 raised= ('RuntimeError', 'no API key configured for pwm_qwen backend')
```

### Not covered by any of this

No live endpoint was contacted at any point. Whether the real
`https://physicsworldmodel.org/qwen/v1` endpoint actually returns `model`,
`system_fingerprint`, and `id` in its SSE chunks is an **unproven premise** that
the entire proof mechanism depends on. All provider behaviour above is
fixture-based.

---

## Amendment 61 Task 3 — strict attestation before semantic output or tools

### Step 0 — four Minor findings from the Task 2 re-review

**M1 (fixed)** `ai4science/harness/adapters/openai.py`. The two lazy module
imports (`transport`, `_dotdict.dot`) sat in the `stream()` generator body,
outside `chunks()` and therefore outside `_parse_stream`'s sequencing. An
unimportable dependency produced `metas=0 seq=[]` — the same blind-guard
condition NEW-1 closed, reached by a different door. Both imports moved inside
`chunks()`.

- Instrument: `tests/test_response_metadata.py::test_openai_stream_module_import_failure_emits_meta_then_holds`.
- RED (pre-fix): `AssertionError: assert [] == [ResponseMeta(...)]` — 1 failed, 12 deselected.
- GREEN (post-fix): 13 passed.
- Mutant `mM1` (imports moved back into the generator body): **KILLED**.

**M2 (fixed)** `ai4science/harness/adapters/base.py:20-27`. The contract now
states that an all-`None` `ResponseMeta` means UNPROVEN, never "a provider was
contacted": "no credential, nothing sent", "the stream closed empty" and "the
provider omitted metadata" produce the identical event. A guard may read the
PRESENCE of a metadata event only as "the adapter reached its sequencing point",
and must decide proven-vs-held on the observed fields alone. `AttestedAdapter`
is written to that rule.

**M3 (fixed)** Two proxy instruments added to `tests/test_llm_proxy.py`:

- `test_proxy_non_json_line_exposes_none_meta_then_fails_closed`
- `test_proxy_bill_before_metadata_exposes_none_meta_then_fails_closed`

Each fixture puts a VALID metadata line *after* the offending line, so dropping
the guard lets the stream recover and release real server evidence — that is
what makes the fixture distinguish fail-closed from silently-skip. Mutants
`mC3` and `mE1`, which had survived every previous round, are now caught.

**M4 (NOT fixed — flagged)** `SEED_MANIFEST.json` is untracked at the worktree
root, is a Task 1 seeding artefact (mtime 2026-08-17 01:44), and is absent from
the Task 2 report's file list. `PROGRESS.md` is untracked at the root for the
same reason. An unqualified `git add -A` would sweep both in. Nothing was
changed; the controller decides.

### Steps 1-3 — `ai4science/harness/route_attestation.py`

Line references are as of 2026-08-18.

- Module docstring (`:1-42`) — states field by field how far the guard reaches: `observed_model` is response-derived AND validated; `system_fingerprint` and `response_id` are response-derived and RECORDED ONLY; `backend` is a CONFIGURED adapter label; the ENDPOINT is not attested at all.
- `EVIDENCE_PROVENANCE` (`:59`) — the same statement in machine-readable form, persisted WITH every evidence record so a later reader cannot mistake `backend` beside `attested: True` for host proof.
- `StrictRouteError(reason)` (`:81`) — `reason` is printable and persistable: backends and models only, never prompt text or credential material.
- `route_evidence(meta, *, required_backend, required_model)` (`:98`) — reachable ONLY after `_validate` returned None. Emits `provenance` (`:109`). Requested and observed model stay under separate keys.
- `_observation_record(meta)` (`:122`) — what a NON-strict route forwards to a sink: `attested: False`, and it stays False.
- `AttestedAdapter` (`:136`) — `_validate` (`:148`) requires the exact backend AND a non-`None` observed model equal to the required one; `_attested` (`:183`) buffers every semantic event until that passes, then emits evidence, yields the metadata, and flushes the buffer. A validation failure keeps draining without releasing anything, so an adapter that raises its OWN error after the metadata still surfaces it verbatim; end of stream then raises `StrictRouteError`. A second metadata event in one request fails closed (`:190-196`). `_passthrough` (`:177`) leaves non-strict routes byte-identical while forwarding an `attested: False` observation record to the sink.
- `record_hold(...)` / `holds()` / `clear_holds()` (`:241`, `:249`, `:253`) — the in-process hold ledger Task 4 will bridge to the Sarsi task lifecycle. `_HOLDS` (`:238`) is process-global and uncapped; see "Recorded, not fixed".

RED for `tests/test_route_attestation.py` was the predicted module-import
failure: `ModuleNotFoundError: No module named 'ai4science.harness.route_attestation'`.
GREEN: **33 passed** (24 at first green; the provenance and hold-capping
instruments were added in the later fix rounds).

### Step 4 — the REPL holds instead of walking the chain

- `repl.py:1133` `_route_adapter()` — a strict agent's session speaks only through the guard. Wired into the parent session (`:1192`), the delegated child session (`:1172`), and the `/model` switch (`:1417`). Ordinary agents get the bare adapter.
- `repl.py:1662-1668` — the turn-failure handler branches: a strict agent records a hold and prints `[harness] research task held: …`; everything else keeps the existing orchestration-chain retry, now under an explicit `else:`.

RED: `assert '[harness] research task held:' in out` failed — the strict session
printed the generic `all models are temporarily unavailable … Retry in a moment.`
GREEN: **11 passed** in `tests/test_harness_repl_strict_route.py` (9 at first
green; +1 for the parent-adapter instrument, +1 for the `/model` instrument
added 2026-08-18).

The Task 1 delegation test needed its stub updated: the delegated child now
speaks through the guard, so its `StubAdapter` script has to PROVE the route the
same way a real provider would. A negative twin was added —
`test_delegated_strict_child_produces_nothing_without_proof` — in which the
child's stub emits no metadata and the parent receives nothing at all.

### Step 5 — the standalone imaging selector is honest under strict mode

`agents/imaging/llm/planner.py:29,33,52` — `LLMImagingPlanner(..., strict=False)`.
In strict mode `_select` re-raises adapter/attestation failures instead of
returning `None`, so `next_step` cannot enter `ReferenceImagingPlanner`. A
silent GAP-TV fallback there is indistinguishable, in every artefact the run
leaves behind, from a research step that really happened. A selection the LLM
simply got wrong is a different thing and still counts as an attempt, so the
deterministic fallback survives for non-strict use.

RED: `TypeError: LLMImagingPlanner.__init__() got an unexpected keyword argument 'strict'` (4 failed, 6 passed). GREEN: 10 passed.

### Round 4 (2026-08-18 fix round) — two real survivors, and a durable battery

The re-review returned FIX with SPEC COMPLIANCE PASS and CODE QUALITY PASS:
record and disclosure only, plus two live mutants nothing in the suite killed.

#### Correction — the recorded rationale for `mD1-mid` was FALSE

An earlier round recorded that the surviving mutant `mD1-mid` (deleting ONLY the
mid-stream fallback emit in `llm_gateway.py:94-96`, immediately before the
`usage` branch) was acceptable because that path "only fires for an adapter that
yields a semantic event without first emitting a `ResponseMeta` — impossible for
the shipped adapters."

**That justification is false.** Only `adapters/openai.py` and
`adapters/proxy.py` emit a `ResponseMeta`. `adapters/anthropic.py`,
`adapters/gemini.py`, `adapters/codex.py` and `adapters/stub.py` do NOT — four
of the six shipped adapters, in direct violation of the `adapters/base.py:15`
contract — and `llm_gateway.health()` (`:52-56`) advertises `anthropic` and
`gemini`. For those backends the FIRST semantic event of EVERY request reaches
the mid-stream emit. It is load-bearing, not defensive.

Driving the real gateway generator with a no-metadata adapter and feeding the
exact gateway bytes into the real `ProxyAdapter`:

```text
UNMUTATED     : wire ['meta','text','tool','usage','done','bill'] -> client OK
mD1-mid-only  : wire ['text','tool','usage','done','meta','bill'] -> RuntimeError:
                proxy semantic event before metadata
```

Consequence: a future refactor of `llm_gateway._gen` that drops or reorders that
emit leaves every test green while every gateway-routed Anthropic/Gemini/Codex
session dies on its first token with `proxy semantic event before metadata`.

Instrument added:
`tests/test_llm_proxy.py::test_gateway_no_metadata_adapter_emits_meta_before_first_semantic_event`.

- RED (mutant applied to a `/tmp` copy): `AssertionError: metadata must precede every semantic event; wire was ['text', 'tool', 'usage', 'done', 'meta', 'bill']` — 1 failed, 19 deselected.
- GREEN (worktree): 20 passed in `tests/test_llm_proxy.py`.
- `mD1-mid` is now **KILLED** (1 failure).

The underlying contract violation — four of six adapters emit no `ResponseMeta`
at all — is a `base.py` / Task 2 surface and was **RECORDED, NOT FIXED** here.
Today only the `imaging` spec is `strict_route`, and it rides the `openai`
adapter, so nothing strict is affected. But if any Anthropic- or Gemini-backed
agent were ever marked `strict_route`, `AttestedAdapter` would hold on EVERY
turn with "no response metadata was observed".

#### `mT9d` — the `/model` switch, and where the guard takes its requirement

`repl.py:1417` is the third call site of `_route_adapter` and had no instrument:
unwrapping it alone left the whole suite green. It is unreachable today only
because `_LOCKED_MENU["pwm_qwen"]` (`repl.py:761`) has ONE entry and the handler
short-circuits on "model unchanged". Safety rested on a menu length, not on an
assertion.

Worse than the missing wrap: the call passed `_route_adapter(new_backend,
new_model, active_spec)`, so the guard took its REQUIRED route from the switch
TARGET rather than from the spec. Add a second `pwm_qwen` menu entry and a
strict agent could `/model` onto it and receive an `AttestedAdapter` that stamps
`attested: True` for a model the strict spec forbids.

**Option (a) was chosen — the stronger fix.** `_route_adapter` (`repl.py:1156-1157`)
now derives a strict agent's required backend and model from the SPEC
(`default_backend` / `default_model`), never from its own arguments. The other
two call sites pass exactly what `effective_route` already derived from the same
spec, so their behaviour is byte-identical; only the `/model` path changes, and
it changes from "attest the destination" to "hold on a forbidden destination".
Option (b) — pin the behaviour with a test and a comment — was not needed: (a)
changed no passing behaviour (all five baselines unchanged).

Instrument added:
`tests/test_harness_repl_strict_route.py::test_model_switch_keeps_a_strict_session_guarded_at_its_spec_route`.
It monkeypatches a second `pwm_qwen` entry into `_LOCKED_MENU`, drives
`/model qwen3.8:8b`, and asserts the live session's adapter is still an
`AttestedAdapter` whose required route is the spec's `pwm_qwen/qwen3.8:27b`.

- RED (pre-fix worktree behaviour): `assert ('pwm_qwen', 'qwen3.8:8b', True) == ('pwm_qwen', 'qwen3.8:27b', True)` — 1 failed, 10 deselected.
- GREEN (post-fix): 11 passed.
- `mT9d` (unwrap the `/model` site) is now **KILLED** (1 failure).
- `mT9e` (take the required route from the caller's target again — i.e. revert option (a)) is also **KILLED** (1 failure), so the regression is pinned in both directions.

#### The mutation battery is now in-repo and re-runnable

`tests/mutation/amendment_61_mutation_battery.py`.

```text
python3 tests/mutation/amendment_61_mutation_battery.py            # all mutants
python3 tests/mutation/amendment_61_mutation_battery.py mT9d mD1-mid
python3 tests/mutation/amendment_61_mutation_battery.py --list
```

It copies the repo to a temporary directory (**the worktree is never mutated**),
applies each mutant as an EXACT textual patch, runs the eight Amendment 61
baseline suites against the copy, records how many tests failed, reverts, and
compares against the manifest. Killed-vs-survived decides the exit status;
`expect_failures` drift is reported but does not fail, because suites grow.

Why it exists: every earlier round's battery lived in `/tmp` and was thrown
away. Two real survivors (`mD1-mid`, `mT9d`) went unnoticed for a full round
because there was nothing to re-run, and five reviewer mutants had to be
reconstructed from prose.

Each mutant carries a `provenance` field. `recorded` means the patch text was
written down when the mutant was first run. `reconstructed` means the id appears
in an earlier round's prose but its patch was never recorded anywhere on disk;
the patch in the battery was rebuilt from the described defect and targets the
same surface, but is not guaranteed byte-identical to what the original reviewer
ran. Five ids are listed as **UNRECOVERED** — `mT6b`, `mX1`, `mX4`, `mX4b`,
`mX5` — because their defects were never described precisely enough to rebuild.
That gap is a named fact in the manifest rather than silent coverage.

Result on the current tree, 2026-08-18:

```text
baseline (unmutated copy): rc=0 104 passed
37/37 matched the manifest — every mutant KILLED, no survivors
unrecovered ids (no patch exists anywhere): mT6b, mX1, mX4, mX4b, mX5
```

Coverage: Task 2 — `mA mB1 mB2 mC1 mC2 mC3 mD1 mD1-mid mE1 mF1 mF2 mG1 mM1`;
Task 3 — `mT1 mT2 mT3 mT4 mT5 mT6 mT7 mT8 mT9 mT9b mT9c mT9d mT9e mT10 mX2 mX3
mX6 mX7 mX8 mX8b mP1 mP2 mP3 mP4`.

Note on the instruments: `mT7` is killed by the generator-level assertion
(`test_strict_route_releases_nothing_at_all_when_evidence_never_arrives`), NOT
by the `run_loop` tool spy — `run_loop` aborts on the raised error before it
reaches tool execution, so the spy alone would not have caught it. The spy earns
its place against `mT10`, where the guard stops raising and the tool really does
run. Both instruments are needed; neither is sufficient.

### Current baseline evidence (2026-08-18)

| suite | passed |
|---|---|
| `tests/test_route_attestation.py` | 33 |
| `tests/test_harness_repl_strict_route.py` | 11 |
| focused four (`test_response_metadata.py`, `test_llm_proxy.py`, `test_harness_adapter_openai.py`, `test_harness_adapter_coverage.py`) | 42 |
| `tests/imaging/test_llm_planner.py` | 10 |
| `tests/test_harness_repl_resilience.py` | 8 |

The whole `tests/` tree is deliberately NOT run: it exceeds two minutes and some
tests attempt network I/O, which is forbidden in this worktree.

### Recorded, not fixed

- **NEW-7** `LLMImagingPlanner` has no production caller: `agents/imaging/agent.py:55,59` builds `ReferenceImagingPlanner`. The strict planner path is instrumented but not reached in production.
- **NEW-8** The evidence sink is never wired in the REPL. `route_evidence()` has no production consumer; Task 4 is the bridge.
- **NEW-9** The guard is per-SESSION, not per-process. `paper_tools.py:59` builds an unguarded adapter. Not reachable for this agent today.
- **NEW-10** Task 1 provenance: `repl.py:1676-1678` now gates the orchestration chain on `brand_autodetected`, so a user who PINS `--backend`/`--model` gets "all models are temporarily unavailable" where the code previously switched brands. Amendment 61 says ordinary non-research operation KEEPS its fallback, and the pinned-route case has no test.
- Four of six shipped adapters (`anthropic`, `gemini`, `codex`, `stub`) emit no `ResponseMeta`, violating `adapters/base.py:15`. See the `mD1-mid` correction above.
- `_observation_record` (`route_attestation.py:122`) carries no `provenance` key, unlike `route_evidence`.
- `_HOLDS` (`route_attestation.py:238`) is process-global and uncapped.
- Two pre-existing failures in `tests/test_console_repl_wiring.py`, unrelated to this diff.
- `SEED_MANIFEST.json` and `PROGRESS.md` are untracked at the repository root; an unqualified `git add -A` sweeps them in.

### Not covered by any of this

No live endpoint was contacted at any point; every provider behaviour above is
fixture-based. Whether the real `https://physicsworldmodel.org/qwen/v1` endpoint
returns `model`, `system_fingerprint` and `id` in its SSE chunks remains the
unproven premise the whole design rests on. Amendment 61 is NOT proven
end-to-end.

**Open OWNER DECISION — the endpoint dimension.** Amendment 61 names three
things to prove: backend, model, and endpoint
`https://physicsworldmodel.org/qwen/v1`. This guard attests exactly ONE of them
from caller-observed evidence: the model the RESPONSE reported.

What that does and does not separate, stated precisely:

- Vertex Qwen is a SEPARATE backend defaulting to `qwen/qwen3-235b-a22b-instruct-2507-maas`. It would FAIL the model check on its own id. An earlier note claiming it evades the guard was wrong and is withdrawn.
- The real gap is TWO HOSTS SERVING THE SAME MODEL ID: Alibaba-hosted Qwen under that tag, a local ollama serving `qwen3.8:27b`, or a misconfigured `base_url` pointing at anything that reports it. The guard cannot tell them apart.
- `system_fingerprint='fp_ollama'` is generic to any ollama host. It is RECORDED and never checked.
- `ResponseMeta` (`events.py:30-37`) has no observed endpoint or base-URL field. The configured `base_url` was deliberately NOT used as proof — that is the configured route string the amendment forbids as evidence.

No endpoint-attestation policy was invented here. The third dimension is
unimplemented and awaits an owner decision.
