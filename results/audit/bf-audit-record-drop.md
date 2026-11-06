# Backfill: dropped audit records

Completed 2026-11-06 on `fleet/bf-audit-record-drop`; no push.
Implementation commit: `2da890debd7496c6efd2d819612d12e975a645df`.
The results file is committed separately after the implementation and checks.

## Scope and behavior

Two sites fixed: the injected audit callbacks in `run_machine` and
`SessionDriver.drive`. A callback raising `Exception` now adds
`audit_failed: <exception type>` to the returned result/verdict. The action,
approval, execution, lease, decision and tripwire behavior are unchanged.
The existing session log carries the annotated verdict too. Successful or
absent audit callbacks retain the original response shape. Exception messages
are not exposed. `docs/DEFECTS.md` records D-002.

## AST audit

The script below inspected both requested trees: 291 broad handlers and 19
handlers surrounding a syntactically named audit/record call. It walks AST
try bodies, including nested statements, rather than matching source lines.
This is a conservative candidate pass: names such as `_record_path` and
`record.get` are included for manual classification; aliases without an
`audit`/`record` spelling are outside its name heuristic. Locations below
refer to the base before the fix. “Keep / follow-up” acknowledges a remaining
silent record gap; it does not claim the handler is correct. The two injected
callbacks were selected for this bounded patch.

All paths in this table are relative to `ai4science/harness/agents/`.

| Site (handler line) | Decision | Finding |
|---|---|---|
| `machine/agent.py:54` | **Fix** | Injected audit callback was swallowed; annotate all four audited returns. |
| `machine/session.py:476` | **Fix** | Injected audit callback was swallowed; annotate verdict and existing log. |
| `machine/hook.py:214` | Keep | Tripwire trust record failure already appears in `unrecorded` and the verdict reason. |
| `machine/hook.py:277` | Keep / follow-up | Owner-decision trust write silently fails; separate internal ledger path, unchanged. |
| `machine/telegram.py:149` | Keep / follow-up | Boolean owner gate silently loses trust write; requires a visibility surface beyond its return boolean. |
| `machine/supervisor.py:130` | Keep | Session-registry file write, not an audit callback. |
| `machine/supervisor.py:314` | Keep | Session-record unlink returns `False` on failure; no audit callback. |
| `machine/supervisor.py:327` | Keep | Registry reap path; failed removal is omitted from returned reaped names. |
| `sarsi/checkpoint.py:126` | Keep | Cleanup then raises `CheckpointNotWritten`; failure is visible. |
| `sarsi/consolidate.py:136` | Keep | Semantic candidate persistence returns `None`; internal memory storage, no injected audit callback. |
| `sarsi/memory.py:186` | Keep / follow-up | Secondary episode failure is soft after authoritative lesson storage; secret rejection re-raises. |
| `sarsi/selfaware.py:950` | Keep / follow-up | Context-manifest file write can silently fail; internal persistence around `route.as_record`. |
| `sarsi/selfaware.py:997` | Keep / follow-up | Routing manifest write can silently fail; documented never-raise behavior needs a separate visibility surface. |
| `sarsi/session.py:314` | Keep / follow-up | Readiness/memory block silently fails; broader than an injected audit callback. |
| `sarsi/session.py:368` | Keep / follow-up | Forecast/memory block has a silent broad fallback; `TooLate` explicitly re-raises. |
| `sarsi/session.py:691` | Keep / follow-up | Success episode persistence silently fails; unchanged internal memory writer. |
| `sarsi/session.py:739` | Keep / follow-up | Timeout episode persistence continues after failure; unchanged internal memory writer. |
| `sarsi/spend.py:201` | Keep | `record.get` is a dictionary read; usage failure becomes an unmeasured outcome, not a dropped audit callback. |
| `sarsi/worker.py:165` | Keep / follow-up | Secondary refusal episode can disappear after directive/report records; unchanged internal memory writer. |
| `machine/session.py:355` (manual check) | Keep | Group cap failure returns the declared ceiling. This is the moved fail-safe described in the brief, not an audit callback; untouched. |

Reproduce from the repository root with the local Python interpreter:

```python
import ast
from pathlib import Path

def broad(handler):
    return handler.type is None or any(
        isinstance(node, ast.Name) and node.id in ('Exception', 'BaseException')
        for node in ast.walk(handler.type)
    )


root = Path('ai4science/harness/agents')
total = candidates = 0
for package in ('machine', 'sarsi'):
    for path in sorted((root / package).rglob('*.py')):
        tree = ast.parse(path.read_text())
        total += sum(isinstance(n, ast.ExceptHandler) and broad(n)
                     for n in ast.walk(tree))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            calls = []
            for statement in node.body:
                for call in ast.walk(statement):
                    if not isinstance(call, ast.Call):
                        continue
                    name = ast.unparse(call.func)
                    if any(word in name.lower() for word in ('audit', 'record')):
                        calls.append(f'{call.lineno}:{name}')
            if not calls:
                continue
            for handler in node.handlers:
                if broad(handler):
                    candidates += 1
                    print(f'{path}:{handler.lineno} calls={",".join(calls)}')
                    print(ast.unparse(ast.Module(body=handler.body, type_ignores=[])))
print(f'broad handlers={total}; audit/record candidates={candidates}')
```

## Test-first evidence

The following seven parameterized cases were run on the unchanged production
base before applying either fix. Every case first compared the action result
or verdict, excluding the proposed additive key, against a normal callback
run; all failed because `audit_failed` was absent (`None` rather than
`RuntimeError`). The callback deliberately raises `RuntimeError`; tests also
check that its message is not exposed.

| Guard case | Action/path verified |
|---|---|
| `test_agent.py` / `capabilities-True` | Read-only detected-capabilities return. |
| `test_agent.py` / `install claude code-False` | Owner refusal (`needs_approval`), zero executions. |
| `test_agent.py` / `login to my account-True` | Credential lease return; same lease count and handle. |
| `test_agent.py` / `install claude code-True` | Approved execution return; same execution count and result. |
| `test_session.py` / `ls -la` | Allow verdict. |
| `test_session.py` / `sudo install example` | Ask verdict. |
| `test_session.py` / `rm -rf /` | Deny + tripwire; next read remains denied by the latched tripwire. |

The session cases each compare a second read call and the tripwire state.
Machine cases compare absent, successful and raising callbacks, preserving the
entire original response except the added key. All callbacks, execution and
broker interactions use local fakes.

Command (same before and after):

```bash
.venv/bin/python -m pytest tests/machine/test_agent.py tests/machine/test_session.py \
  -q -ra -k test_audit_failure_is_visible
```

RED output, abridged to the failure assertion and exact failed node list
(runtime object representations omitted):

```text
FFFFFFF                                                                  [100%]
E           AssertionError: assert None == 'RuntimeError'
FAILED tests/machine/test_agent.py::test_audit_failure_is_visible_without_changing_the_action[capabilities-True]
FAILED tests/machine/test_agent.py::test_audit_failure_is_visible_without_changing_the_action[install claude code-False]
FAILED tests/machine/test_agent.py::test_audit_failure_is_visible_without_changing_the_action[login to my account-True]
FAILED tests/machine/test_agent.py::test_audit_failure_is_visible_without_changing_the_action[install claude code-True]
FAILED tests/machine/test_session.py::test_audit_failure_is_visible_without_changing_the_verdict_or_tripwire[ls -la]
FAILED tests/machine/test_session.py::test_audit_failure_is_visible_without_changing_the_verdict_or_tripwire[sudo install example]
FAILED tests/machine/test_session.py::test_audit_failure_is_visible_without_changing_the_verdict_or_tripwire[rm -rf /]
```

GREEN output (exit 0):

```text
.......                                                                  [100%]
```

RED: 7 failed. GREEN: 7 passed. Pytest's configured quiet option together with
`-q` suppresses the numerical footer; counts above are from the outcome marks.

## Original-suite comparison

Baseline: unchanged production code, with the newly added guards excluded.
After: both fixes plus all seven new cases. The same four original failures
and four skips remain; there are no new failures or errors.

| Suite | Before passed | After passed | Before / after failed | Before / after skipped |
|---|---:|---:|---:|---:|
| `tests/machine` | 154 | 161 | 0 / 0 | 1 / 1 |
| `tests/sarsi` | 2410 | 2410 | 4 / 4 | 3 / 3 |
| Total | 2564 | 2571 | 4 / 4 | 4 / 4 |

The machine skip is a collection-time skip. The three SARSI skips are opt-in
live tests, which were not enabled. Excluding the seven new passing cases,
the original outcomes have exactly the same counts. Baseline counts were
counted from pytest progress marks and skip summaries; post-change counts
were also checked against local JUnit XML. Both full runs exited 1 because
of the four original failures.

Commands:

```bash
# Before, while production files still matched the base:
.venv/bin/python -m pytest tests/machine tests/sarsi -q -ra \
  -k 'not test_audit_failure_is_visible'
# After, including the seven new guards:
.venv/bin/python -m pytest tests/machine tests/sarsi -q -ra \
  --junitxml=tmp/after.xml
```

The same summary lines appear in both runs:

```text
SKIPPED [1] tests/machine/test_machine_foundry.py:15: could not import 'pwm_control_plane': No module named 'pwm_control_plane'
SKIPPED [1] tests/sarsi/test_live_acp_e2e.py:47: set SARSI_LIVE_TEST=1 to run
SKIPPED [1] tests/sarsi/test_live_acp_e2e.py:72: set SARSI_LIVE_TEST=1 to run
SKIPPED [1] tests/sarsi/test_live_e2e.py:54: set SARSI_LIVE_TEST=1 to run
FAILED tests/sarsi/test_backends.py::test_both_backends_exist_and_name_a_real_spec
FAILED tests/sarsi/test_imaging_agent_in_the_roster.py::test_it_is_built_on_the_field_spec_that_actually_exists
FAILED tests/sarsi/test_m5_memory_utility.py::test_context_is_longer_with_memory
FAILED tests/sarsi/test_writable_in_tool_description.py::test_the_spec_built_registry_carries_them_too
```

Three failures concern unavailable optional specs (`claude-code`,
`computational-imaging`, `unified-LLM`); the memory test asserts that adding
memory cannot shorten context. These pre-existing failures were left outside
the two-site patch.

## Local setup and limits

Continued the existing bundle checkout on the requested branch with unchanged
tracked base files. Used the previously authorized `uv` setup route for the
existing local virtual environment and installed the editable `.[dev]` extra.
**Added for test collection:** `uvicorn==0.54.0`; its newly installed transitive
dependency was `click==8.5.1`. Neither was added to project dependencies.
The earlier collection error was `ModuleNotFoundError: No module named
'uvicorn'`; no extra production dependency change was needed.

Commands ran at nice 19 with `OPENBLAS_NUM_THREADS=1`, `OMP_NUM_THREADS=1`
and `MKL_NUM_THREADS=1`. Pytest ran serially (one worker, below half of eight
available cores). Cache, pytest temporary directories and local logs stayed
under `./tmp`; raw logs and JUnit XML are not committed. No model calls, paid
APIs, cloud compute, datasets or live-test opt-ins were used. No push was made.
`git diff --check` passed. The implementation commit changes only the two
fixed production sites, their existing test files and `docs/DEFECTS.md`.
This report was written last after verification and the implementation commit.
