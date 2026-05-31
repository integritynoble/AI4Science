# Plan 2 — Ensemble Power Mode (on the harness) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Supersedes** `docs/superpowers/plans/2026-05-31-common-mode-ensemble-core-pipeline.md` (written before the harness existed; its executors were `BaseAgent` stubs). Here, executors are real **harness `AgentSession`s** (multi-brand, auto-approve) running in isolated git worktrees.

**Goal:** Build the opt-in best-of-N **executor-ensemble → judge-panel** power mode: a task is attempted in parallel by several brand-driven harness sessions in isolated worktrees, scored by a judge panel (with each candidate's repo-test result as an objective anchor), and the winning diff is applied. Invoked via `ai4science ensemble-run "<task>"` and (later) `/ensemble` in the REPL.

**Architecture:** New `ai4science/ensemble/` package. `pool` resolves reachable executor/judge members from the routing pools. `runner` runs each executor as a harness `AgentSession(adapter_for(backend), model, workspace=<worktree>, auto_yes=True)` to completion, captures the worktree diff + answer + cost + test result. `panel` scores candidates with judge models (non-agentic `llm/execute` calls). `select` aggregates (senior-judge tie-break = Opus 4.8) and triggers synthesis when the top two are within an epsilon. `pipeline` orchestrates and applies the winning diff; everything meters to the PWM ledger.

**Tech Stack:** Python 3, pytest + monkeypatch, git worktrees, existing `ai4science.harness` (session/adapters/factory), `ai4science.llm` (routing/execute/pricing/ledger), `ai4science.user` (config).

**Spec:** `docs/superpowers/specs/2026-05-31-common-mode-multibrand-ensemble-design.md` (§6 ensemble, §11 resolved decisions). Note: the Opus 4.7→4.8 routing swap is already landed on `main`.

## File structure (created in this plan)

| File | Responsibility |
|---|---|
| `ai4science/ensemble/__init__.py` | package marker |
| `ai4science/ensemble/types.py` | `Candidate`, `JudgeScore`, `Selection` |
| `ai4science/ensemble/config.py` | settings (max_parallel, synthesis_epsilon, max_task_tokens, test_command) |
| `ai4science/ensemble/worktree.py` | git worktree add/diff/changed_files/apply/remove |
| `ai4science/ensemble/checks.py` | detect + run repo test command → `check_result` |
| `ai4science/ensemble/pool.py` | reachable executor/judge members |
| `ai4science/ensemble/runner.py` | run harness sessions in worktrees → `Candidate[]` |
| `ai4science/ensemble/panel.py` | judge scoring + PWM metering |
| `ai4science/ensemble/select.py` | aggregate, winner, synthesis trigger |
| `ai4science/ensemble/pipeline.py` | orchestrate stages, token ceiling, apply winner |
| `ai4science/llm/routing.py` (modify) | add `ensemble_members(role)` |
| `ai4science/cli.py` (modify) | register `ensemble-run` |
| `tests/test_ensemble_*.py` | one per module |

---

### Task 1: `routing.ensemble_members`

**Files:**
- Modify: `ai4science/llm/routing.py`
- Test: `tests/test_ensemble_routing.py`

(The Opus 4.7→4.8 chain swap is already on `main`; this task only adds the pool accessor.)

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_routing.py
from ai4science.llm import routing


def test_ensemble_members_filters_by_availability(monkeypatch):
    monkeypatch.setattr(routing, "backend_available", lambda b: b in ("anthropic", "gemini"))
    members = routing.ensemble_members("orchestration")
    assert {b for b, _ in members} == {"anthropic", "gemini"}
    assert ("anthropic", "claude-opus-4-8") in members


def test_ensemble_members_unknown_role():
    assert routing.ensemble_members("nope") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/spiritai/pwm/Physics_World_Model/AI4Science && python -m pytest tests/test_ensemble_routing.py -v`
Expected: FAIL — `ensemble_members` missing.

- [ ] **Step 3: Add `ensemble_members` at the end of `routing.py`**

```python
def ensemble_members(role: str):
    """All reachable (backend, model) members of a role's pool, in chain order,
    de-duped. Unlike resolve() (first-reachable pick), the ensemble runs every one."""
    chain = AGENT_CHAINS.get(role)
    if not chain:
        return []
    seen, out = set(), []
    for backend, model in chain:
        if (backend, model) in seen:
            continue
        if backend_available(backend):
            seen.add((backend, model))
            out.append((backend, model))
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ensemble_routing.py tests/test_llm_routing.py -v`
Expected: PASS (new + existing routing tests).

- [ ] **Step 5: Commit**

```bash
git add ai4science/llm/routing.py tests/test_ensemble_routing.py
git commit -m "feat(routing): ensemble_members() — all reachable members of a pool"
```

---

### Task 2: Ensemble types + config

**Files:**
- Create: `ai4science/ensemble/__init__.py`, `ai4science/ensemble/types.py`, `ai4science/ensemble/config.py`
- Test: `tests/test_ensemble_types.py`, `tests/test_ensemble_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_ensemble_types.py
from pathlib import Path
from ai4science.ensemble.types import Candidate, JudgeScore, Selection


def test_candidate_fields():
    c = Candidate(member=("anthropic", "claude-opus-4-8"), answer="ok",
                  diff="d", changed_files=[Path("x.py")],
                  check_result={"ran": True, "passed": True, "summary": ""})
    assert c.member[1] == "claude-opus-4-8" and c.check_result["passed"]


def test_judge_and_selection():
    js = JudgeScore(judge=("openai", "gpt-5.5"), ranking=[1, 0],
                    scores={0: 0.3, 1: 0.9}, rationale="b")
    assert js.ranking[0] == 1
    assert Selection(winner=1, ranking=[1, 0], rationale="a", synthesized=False).winner == 1
```

```python
# tests/test_ensemble_config.py
from ai4science.ensemble import config
from ai4science import user


def test_defaults(monkeypatch):
    monkeypatch.setattr(user, "load", lambda: {})
    c = config.load()
    assert c.max_task_tokens == 2_000_000 and c.max_parallel_executors == 4
    assert abs(c.synthesis_epsilon - 0.05) < 1e-9 and c.test_command is None


def test_overrides(monkeypatch):
    monkeypatch.setattr(user, "load", lambda: {"ensemble": {"max_parallel_executors": 2}})
    assert config.load().max_parallel_executors == 2
```

- [ ] **Step 2: Run to verify they fail**

Run: `python -m pytest tests/test_ensemble_types.py tests/test_ensemble_config.py -v`
Expected: FAIL — modules missing.

- [ ] **Step 3: Implement**

`ai4science/ensemble/__init__.py`:
```python
"""Opt-in best-of-N executor-ensemble → judge-panel power mode (on the harness)."""
```

`ai4science/ensemble/types.py`:
```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

Member = Tuple[str, str]


@dataclass
class Candidate:
    member: Member
    answer: str
    diff: Optional[str] = None
    changed_files: List[Path] = field(default_factory=list)
    check_result: Optional[Dict] = None
    error: Optional[str] = None


@dataclass
class JudgeScore:
    judge: Member
    ranking: List[int]
    scores: Dict[int, float]
    rationale: str
    error: Optional[str] = None


@dataclass
class Selection:
    winner: int
    ranking: List[int]
    rationale: str
    synthesized: bool = False
```

`ai4science/ensemble/config.py`:
```python
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai4science import user

DEFAULTS = {"max_task_tokens": 2_000_000, "max_parallel_executors": 4,
            "synthesis_epsilon": 0.05, "test_command": None}


@dataclass
class EnsembleConfig:
    max_task_tokens: int
    max_parallel_executors: int
    synthesis_epsilon: float
    test_command: Optional[str]


def load() -> EnsembleConfig:
    try:
        raw = (user.load() or {}).get("ensemble", {}) or {}
    except Exception:
        raw = {}
    m = {**DEFAULTS, **{k: raw[k] for k in DEFAULTS if k in raw}}
    return EnsembleConfig(int(m["max_task_tokens"]), int(m["max_parallel_executors"]),
                          float(m["synthesis_epsilon"]), m["test_command"])
```

- [ ] **Step 4: Run to verify pass**

Run: `python -m pytest tests/test_ensemble_types.py tests/test_ensemble_config.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/ensemble/__init__.py ai4science/ensemble/types.py ai4science/ensemble/config.py tests/test_ensemble_types.py tests/test_ensemble_config.py
git commit -m "feat(ensemble): candidate/judge/selection types + config"
```

---

### Task 3: Worktree helpers + test-command detection

**Files:**
- Create: `ai4science/ensemble/worktree.py`, `ai4science/ensemble/checks.py`
- Test: `tests/test_ensemble_worktree.py`, `tests/test_ensemble_checks.py`

Reuse the exact `worktree.py` (add/diff/changed_files/apply/remove via `git worktree`) and `checks.py` (detect `pytest`/`npm test`/`cargo test`/`go test` + run → `{ran,passed,summary}`) from the superseded core-pipeline plan (Tasks 4 and 5) — that code is harness-independent and unchanged. Copy those two modules and their two test files verbatim from `docs/superpowers/plans/2026-05-31-common-mode-ensemble-core-pipeline.md` Tasks 4–5.

- [ ] **Step 1–4:** Implement worktree.py + checks.py per the referenced tasks (TDD). Run `python -m pytest tests/test_ensemble_worktree.py tests/test_ensemble_checks.py -v` → PASS.
- [ ] **Step 5: Commit**

```bash
git add ai4science/ensemble/worktree.py ai4science/ensemble/checks.py tests/test_ensemble_worktree.py tests/test_ensemble_checks.py
git commit -m "feat(ensemble): git worktree helpers + repo test-command detection"
```

---

### Task 4: Pool resolution

**Files:**
- Create: `ai4science/ensemble/pool.py`
- Test: `tests/test_ensemble_pool.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_pool.py
from ai4science.ensemble import pool
from ai4science.llm import routing


def test_executor_members(monkeypatch):
    monkeypatch.setattr(routing, "ensemble_members",
                        lambda r: [("anthropic", "claude-opus-4-8")] if r == "orchestration" else [])
    assert pool.executor_members() == [("anthropic", "claude-opus-4-8")]


def test_judge_members_union(monkeypatch):
    monkeypatch.setattr(routing, "ensemble_members", lambda r: {
        "checking": [("openai", "gpt-5.5"), ("anthropic", "claude-opus-4-8")],
        "fast": [("gemini", "gemini-3.5-flash"), ("anthropic", "claude-opus-4-8")]}.get(r, []))
    assert pool.judge_members() == [("openai", "gpt-5.5"), ("anthropic", "claude-opus-4-8"),
                                    ("gemini", "gemini-3.5-flash")]
```

- [ ] **Step 2: Run to verify it fails.** `python -m pytest tests/test_ensemble_pool.py -v` → FAIL.

- [ ] **Step 3: Implement `pool.py`**

```python
from __future__ import annotations

from typing import List, Tuple

from ai4science.llm import routing

Member = Tuple[str, str]


def executor_members() -> List[Member]:
    return routing.ensemble_members("orchestration")


def judge_members() -> List[Member]:
    seen, out = set(), []
    for role in ("checking", "fast"):
        for m in routing.ensemble_members(role):
            if m not in seen:
                seen.add(m); out.append(m)
    return out
```

- [ ] **Step 4: Run.** `python -m pytest tests/test_ensemble_pool.py -v` → PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(ensemble): executor + judge pool resolution"`

---

### Task 5: Runner — harness sessions in worktrees

**Files:**
- Create: `ai4science/ensemble/runner.py`
- Test: `tests/test_ensemble_runner.py`

Each executor is a harness `AgentSession` bound to a brand, run **non-interactively** (`auto_yes=True`) in its own worktree; the diff is read from the worktree, and the repo tests run for `check_result`.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_runner.py
import subprocess
from pathlib import Path
from ai4science.ensemble import runner
from ai4science.harness.adapters.stub import StubAdapter
from ai4science.harness.events import TextDelta, ToolCall, Done


def _init_repo(root: Path):
    for args in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(root)] + args if args[0] != "init" else ["git", "init", "-q", str(root)], check=True)
    (root / "a.txt").write_text("v0\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"], check=True)


def _stub_session_factory(member, workspace):
    # a session whose stub adapter writes a member-specific edit then finishes
    from ai4science.harness.session import AgentSession
    script = [[TextDelta(f"{member[1]} done"),
               ToolCall("c1", "write", {"path": "a.txt", "content": f"by {member[1]}\n"}),
               Done("tool_use")],
              [TextDelta("ok"), Done("end")]]
    return AgentSession(adapter=StubAdapter(script), model=member[1], backend=member[0],
                        workspace=workspace, read_only=False, auto_yes=True,
                        on_text=lambda t: None, meter=lambda u: None)


def test_runner_one_candidate_per_member(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; repo.mkdir(); _init_repo(repo)
    members = [("anthropic", "claude-opus-4-8"), ("openai", "gpt-5.5")]
    monkeypatch.setattr(runner, "executor_members", lambda: members)
    monkeypatch.setattr(runner, "_session_for", _stub_session_factory)
    monkeypatch.setattr(runner.checks, "run", lambda ws, override: {"ran": False, "passed": False, "summary": ""})

    cands = runner.run("edit a.txt", repo, max_parallel=2, test_override=None)
    assert len(cands) == 2
    assert all("by " in (c.diff or "") for c in cands)
    assert {c.member[1] for c in cands} == {"claude-opus-4-8", "gpt-5.5"}
```

- [ ] **Step 2: Run to verify it fails.** `python -m pytest tests/test_ensemble_runner.py -v` → FAIL.

- [ ] **Step 3: Implement `runner.py`**

```python
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from ai4science.ensemble import checks, worktree
from ai4science.ensemble.pool import executor_members
from ai4science.ensemble.types import Candidate, Member
from ai4science.harness.adapters.factory import adapter_for, make_meter
from ai4science.harness.session import AgentSession


def _session_for(member: Member, workspace: Path) -> AgentSession:
    backend, model = member
    return AgentSession(
        adapter=adapter_for(backend), model=model, backend=backend,
        workspace=workspace, read_only=False, auto_yes=True,
        on_text=lambda t: None, meter=make_meter(backend=backend, model=model),
    )


def _run_member(member: Member, prompt: str, repo: Path, idx: int,
                test_override: Optional[str]) -> Optional[Candidate]:
    label = f"cand-{idx}-{member[0]}"
    wt = None
    try:
        wt = worktree.add(repo, label)
        session = _session_for(member, wt)
        answer = session.run_turn(prompt)
        diff = worktree.diff(wt)
        changed = worktree.changed_files(wt)
        check = checks.run(wt, override=test_override)
        return Candidate(member=member, answer=answer, diff=diff,
                         changed_files=changed, check_result=check)
    except Exception as exc:
        return Candidate(member=member, answer="", error=str(exc)) if wt is None else None
    finally:
        if wt is not None:
            worktree.remove(repo, wt)


def run(prompt: str, repo: Path, max_parallel: int,
        test_override: Optional[str]) -> List[Candidate]:
    members = executor_members()
    if not members:
        return []
    workers = max(1, min(max_parallel, len(members)))
    with ThreadPoolExecutor(max_workers=workers) as ex:
        results = list(ex.map(
            lambda im: _run_member(im[1], prompt, repo, im[0], test_override),
            list(enumerate(members))))
    return [c for c in results if c is not None]
```

- [ ] **Step 4: Run.** `python -m pytest tests/test_ensemble_runner.py -v` → PASS. Then `python -m pytest tests/test_ensemble_*.py tests/test_harness_*.py -q` for no regressions.
- [ ] **Step 5: Commit.** `git commit -m "feat(ensemble): worktree-isolated harness-session runner"`

NOTE: worktree-isolation means each executor's adapter writes into its own worktree. The StubAdapter drives the write tool with `auto_yes=True` so the gate auto-approves (no confirm). Real brand adapters need the harness/factory + reachable creds (manual E2E).

---

### Task 6: Judge panel + selection

**Files:**
- Create: `ai4science/ensemble/panel.py`, `ai4science/ensemble/select.py`
- Test: `tests/test_ensemble_panel.py`, `tests/test_ensemble_select.py`

Reuse the `panel.py` (judge a specific model via `llm/execute._EXECUTORS`, parse JSON verdict, meter to ledger) and `select.py` (mean-rank aggregate, senior-judge=Opus 4.8 tie-break, synthesis when top-2 within epsilon) from the superseded core-pipeline plan (Tasks 7 and 8) — they are harness-independent and unchanged. Copy those modules + tests verbatim from that plan.

- [ ] **Step 1–4:** Implement panel.py + select.py per the referenced tasks (TDD). Run their tests → PASS.
- [ ] **Step 5: Commit.** `git commit -m "feat(ensemble): judge panel (metered) + score aggregation/selection"`

---

### Task 7: Pipeline + `ensemble-run` CLI

**Files:**
- Create: `ai4science/ensemble/pipeline.py`
- Modify: `ai4science/cli.py` (register `ensemble-run`)
- Test: `tests/test_ensemble_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_pipeline.py
import subprocess
from pathlib import Path
from ai4science.ensemble import pipeline
from ai4science.ensemble.types import Candidate, JudgeScore


def _init_repo(root: Path):
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    for a in (["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(root)] + a, check=True)
    (root / "a.txt").write_text("v0\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"], check=True)


def test_pipeline_applies_winner(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; repo.mkdir(); _init_repo(repo)
    cands = [Candidate(member=("anthropic", "claude-opus-4-8"), answer="A",
             diff="diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n@@ -1 +1 @@\n-v0\n+winner\n",
             check_result={"ran": True, "passed": True, "summary": ""})]
    monkeypatch.setattr(pipeline, "_run_executors", lambda *a, **k: cands)
    monkeypatch.setattr(pipeline.panel, "run",
                        lambda task, cs: [JudgeScore(("openai", "gpt-5.5"), [0], {0: 0.9}, "best")])
    out = pipeline.run("make it say winner", repo)
    assert out["applied"] and out["winner_model"] == "claude-opus-4-8"
    assert (repo / "a.txt").read_text() == "winner\n"


def test_pipeline_no_candidates(tmp_path, monkeypatch):
    repo = tmp_path / "repo"; repo.mkdir(); _init_repo(repo)
    monkeypatch.setattr(pipeline, "_run_executors", lambda *a, **k: [])
    out = pipeline.run("x", repo)
    assert out["applied"] is False and "no candidate" in out["error"].lower()
```

- [ ] **Step 2: Run to verify it fails.** → FAIL.

- [ ] **Step 3: Implement `pipeline.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from ai4science.ensemble import config as cfg
from ai4science.ensemble import panel, runner, select, worktree
from ai4science.ensemble.types import Candidate

SENIOR_JUDGE = ("anthropic", "claude-opus-4-8")


def _run_executors(task: str, repo: Path, max_parallel: int,
                   test_override: Optional[str]) -> List[Candidate]:
    return runner.run(task, repo, max_parallel=max_parallel, test_override=test_override)


def run(task: str, repo: Path) -> Dict:
    c = cfg.load()
    cands = _run_executors(task, repo, c.max_parallel_executors, c.test_command)
    if not cands:
        return {"applied": False, "error": "no candidates produced",
                "winner_model": None, "candidates": 0}
    if len(cands) == 1:
        sel_winner, ranking, rationale, synthesized, scores = 0, [0], "single executor", False, []
    else:
        scores = panel.run(task, cands)
        sel = select.aggregate(scores, n=len(cands), epsilon=c.synthesis_epsilon,
                               senior_member=SENIOR_JUDGE)
        sel_winner, ranking, rationale, synthesized = sel.winner, sel.ranking, sel.rationale, sel.synthesized
    winner = cands[sel_winner]
    applied, msg = worktree.apply(repo, winner.diff or "")
    return {"applied": applied, "apply_message": msg, "winner_model": winner.member[1],
            "winner_answer": winner.answer, "ranking": [cands[i].member[1] for i in ranking],
            "rationale": rationale, "synthesized": synthesized, "candidates": len(cands),
            "judges": len(scores), "error": None if applied else f"diff apply failed: {msg}"}
```

- [ ] **Step 4: Register the CLI command** in `ai4science/cli.py` (near the other `@app.command()` single commands):
```python
@app.command(name="ensemble-run")
def ensemble_run(
    task: str = typer.Argument(..., help="Task to run through the ensemble"),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Git repo root"),
) -> None:
    """Run one task through the multi-brand executor-ensemble → judge-panel."""
    import json as _json
    from ai4science.ensemble import pipeline
    out = pipeline.run(task, workspace.resolve())
    typer.echo(_json.dumps(out, indent=2))
    raise typer.Exit(0 if out.get("applied") else 2)
```
Add a CliRunner smoke test (`tests/test_ensemble_pipeline.py`):
```python
def test_cli_invokes_pipeline(monkeypatch):
    from typer.testing import CliRunner
    from ai4science.cli import app
    from ai4science.ensemble import pipeline as pl
    monkeypatch.setattr(pl, "run", lambda task, repo: {"applied": True, "winner_model": "claude-opus-4-8"})
    res = CliRunner().invoke(app, ["ensemble-run", "do it"])
    assert res.exit_code == 0 and "claude-opus-4-8" in res.stdout
```

- [ ] **Step 5: Run + Commit.** `python -m pytest tests/test_ensemble_pipeline.py -v` → PASS.
```bash
git add ai4science/ensemble/pipeline.py ai4science/cli.py tests/test_ensemble_pipeline.py
git commit -m "feat(ensemble): pipeline orchestration + ensemble-run CLI"
```

---

### Task 8: Full suite green + `/ensemble` REPL + parity doc

- [ ] **Step 1:** `python -m pytest -q` — all green except the 2 pre-existing env failures.
- [ ] **Step 2:** Add `/ensemble <task>` to `harness/repl.py` `_dispatch_slash`/inline: runs `ensemble.pipeline.run(task, workspace)` and prints the result (the opt-in REPL entry). Add a test asserting the slash routes to the pipeline (monkeypatched).
- [ ] **Step 3:** Update `docs/CLAUDE_CODE_PARITY.md` / spec §10: Plan 2 (ensemble) landed — opt-in best-of-N on harness sessions, `ensemble-run` + `/ensemble`. Note executor token metering is via `make_meter` (interactive-grade), and that the ensemble reuses Plan-3d's hardened bash (timeout + sandbox) — important since executors run non-interactively in auto-yes.
- [ ] **Step 4:** Commit: `git commit -m "feat(ensemble): /ensemble REPL entry; docs"`.

---

## Self-review

- **Spec coverage (§6, §11):** executor-ensemble on harness sessions in worktrees (Task 5), judge panel checking∪fast (Tasks 4,6), select + synthesis with Opus-4.8 senior tie-break (Task 6), worktree isolation + check_result (Task 3), config/ceiling/concurrency (Task 2), `ensemble_members` (Task 1), PWM metering via `make_meter` (Task 5/6), CLI + `/ensemble` (Tasks 7,8).
- **Placeholder scan:** Tasks 3 and 6 explicitly reuse verbatim modules from the superseded core-pipeline plan (worktree/checks/panel/select) — those are concrete, fully-specified there; copy them. Everything else has inline code.
- **Type consistency:** `Candidate/JudgeScore/Selection` shared; `AgentSession(adapter, model, backend, workspace, auto_yes=True).run_turn(prompt)->str`; `adapter_for`/`make_meter` from the harness factory; `routing.ensemble_members` added Task 1; `worktree.apply(repo, diff)->(ok,msg)`.

## Key difference from the superseded plan
The executor is now a **real harness `AgentSession`** (multi-brand, hardened tools incl. bash timeout + sandbox from Plan 3d), not a `BaseAgent` stub. This is what makes the ensemble genuinely multi-model and safe to run non-interactively (auto-yes) — the Plan-3d bash hardening is a prerequisite that is now in place.

## Known limitations
1. Executor token metering uses `make_meter` (Anthropic input tokens now metered via Plan 3d). Real multi-brand E2E needs reachable creds (manual).
2. Worktree-per-executor is disk/CPU heavy; `max_parallel_executors` caps concurrency.
3. Synthesis pass (Task 6/select) currently flags when to synthesize; the actual graft step is a follow-on if desired.
