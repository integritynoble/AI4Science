# Common-Mode Ensemble — Power Mode (Plan 2 of 3) Implementation Plan

> **⛔ SUPERSEDED (2026-05-31)** by `docs/superpowers/plans/2026-05-31-plan2-ensemble-on-harness.md`,
> which builds executors on the now-existing native harness `AgentSession`s (multi-brand,
> Plan-3d-hardened) instead of the `BaseAgent` stubs used below. Keep this file only as the
> source for the verbatim `worktree.py` / `checks.py` / `panel.py` / `select.py` modules that
> the new Plan 2 reuses (Tasks 4, 5, 7, 8 here).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **REDESIGN NOTE (2026-05-31):** Common mode's *default* is now the interactive native
> harness (Plan 1, `2026-05-31-native-interactive-harness.md`) — the Claude Code experience.
> This ensemble is the **opt-in power mode** (`/ensemble`, or `ensemble-run`), NOT the default.
> Executors here will eventually be **harness `AgentSession`s in auto-approve mode** bound to a
> brand (built in Plan 1). Until Plan 1 lands, the runner uses the existing `ClaudeAgent` +
> stub executors to exercise the pool/panel/select machinery — see `_agent_for` in Task 9.
> This plan is unchanged below except for this scoping; build it AFTER Plan 1.

**Goal:** Build the opt-in multi-brand executor-ensemble → judge-panel → select/apply best-of-N pipeline for AI4Science common mode, proven end-to-end with stub executors, runnable via an `ensemble-run` CLI entry and (post-Plan-1) a `/ensemble` REPL command.

**Architecture:** A new `ai4science/ensemble/` package orchestrates: (1) a **pool** of reachable executor/judge models from the routing roles; (2) a **runner** that runs each executor in its own git worktree, computes a diff, and runs the repo's tests for an objective signal; (3) a **panel** of judge models that score candidates; (4) a **select** stage that aggregates scores, picks a winner, and optionally synthesizes. The pipeline applies the winner's diff and meters judge calls to the PWM ledger. Executors become harness sessions once Plan 1 ships.

**Tech Stack:** Python 3, Typer (CLI), pytest + monkeypatch (tests), git worktrees (subprocess), existing `ai4science.llm` routing/execute/pricing/ledger and `ai4science.agents` modules.

**Spec:** `docs/superpowers/specs/2026-05-31-common-mode-multibrand-ensemble-design.md`

---

## Scope notes & decisions carried from the spec

- **Always-ensemble:** every common-mode task runs the full reachable executor pool. No soft throttle; a generous per-task token ceiling (default 2,000,000) is the only backstop.
- **Judge panel = `checking ∪ fast`** reachable members. Senior-judge tie-break = `claude-opus-4-8`.
- **Synthesis** runs only when the top-two aggregate scores are within `synthesis_epsilon` (config; default 0.05).
- **Executor concurrency** = config `max_parallel_executors` (default 4).
- **`check_result`** test command auto-detected (`pytest` → `npm test` → `cargo test` → `go test`), with a per-workspace override; omitted if none found.
- **Two `AgentResult` types already exist** — do NOT modify them. The ensemble defines its own `Candidate`/`JudgeScore`/`Selection` in `ensemble/types.py`.
- **Executor token metering is deferred to Plan 2.** `BaseAgent.run_task` does not surface token usage today, so Plan 1 meters **judge** calls (which return usage via `execute._EXECUTORS`) and records executors with empty usage (ledger tolerates this). This is a scoped limitation, documented, not a placeholder.

## File structure (created in this plan)

| File | Responsibility |
|---|---|
| `ai4science/ensemble/__init__.py` | package marker + public exports |
| `ai4science/ensemble/types.py` | `Candidate`, `JudgeScore`, `Selection` dataclasses |
| `ai4science/ensemble/config.py` | ensemble settings (read from `user.load()`), with defaults |
| `ai4science/ensemble/worktree.py` | git worktree add/remove + diff/apply helpers |
| `ai4science/ensemble/checks.py` | detect + run the repo's test command → `check_result` |
| `ai4science/ensemble/pool.py` | reachable executor/judge `(backend, model)` members |
| `ai4science/ensemble/panel.py` | call a specific judge model + parse score; run the panel |
| `ai4science/ensemble/select.py` | aggregate scores, pick winner, synthesis trigger |
| `ai4science/ensemble/runner.py` | run executors in worktrees → `Candidate[]` |
| `ai4science/ensemble/pipeline.py` | orchestrate stages, token ceiling, apply winner |
| `tests/test_ensemble_*.py` | one test file per module above |

Modified: `ai4science/llm/routing.py` (Opus 4.7→4.8, add `ensemble_members`), `ai4science/cli.py` (register `ensemble-run`).

---

### Task 1: Ensemble data types

**Files:**
- Create: `ai4science/ensemble/__init__.py`
- Create: `ai4science/ensemble/types.py`
- Test: `tests/test_ensemble_types.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_types.py
from pathlib import Path
from ai4science.ensemble.types import Candidate, JudgeScore, Selection


def test_candidate_fields():
    c = Candidate(
        member=("anthropic", "claude-opus-4-8"),
        answer="done",
        diff="--- a\n+++ b\n",
        changed_files=[Path("x.py")],
        check_result={"ran": True, "passed": True, "summary": "1 passed"},
        worktree=Path("/tmp/wt"),
        error=None,
    )
    assert c.member[1] == "claude-opus-4-8"
    assert c.check_result["passed"] is True


def test_judgescore_and_selection():
    js = JudgeScore(
        judge=("openai", "gpt-5.5"),
        ranking=[1, 0],
        scores={0: 0.4, 1: 0.9},
        rationale="cand 1 passes tests",
    )
    assert js.ranking[0] == 1
    sel = Selection(winner=1, ranking=[1, 0], rationale="agg", synthesized=False)
    assert sel.winner == 1 and sel.synthesized is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /home/spiritai/pwm/Physics_World_Model/AI4Science && python -m pytest tests/test_ensemble_types.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'ai4science.ensemble'`

- [ ] **Step 3: Create the package and types**

```python
# ai4science/ensemble/__init__.py
"""Multi-brand executor-ensemble → judge-panel pipeline for common mode."""
```

```python
# ai4science/ensemble/types.py
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

Member = Tuple[str, str]  # (backend, model)


@dataclass
class Candidate:
    member: Member
    answer: str
    diff: Optional[str] = None
    changed_files: List[Path] = field(default_factory=list)
    check_result: Optional[Dict] = None   # {"ran": bool, "passed": bool, "summary": str}
    worktree: Optional[Path] = None
    error: Optional[str] = None


@dataclass
class JudgeScore:
    judge: Member
    ranking: List[int]            # candidate indices, best -> worst
    scores: Dict[int, float]      # candidate index -> 0..1
    rationale: str
    error: Optional[str] = None


@dataclass
class Selection:
    winner: int                   # candidate index
    ranking: List[int]
    rationale: str
    synthesized: bool = False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ensemble_types.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/ensemble/__init__.py ai4science/ensemble/types.py tests/test_ensemble_types.py
git commit -m "feat(ensemble): candidate/judge/selection data types"
```

---

### Task 2: Routing — Opus 4.8 swap + `ensemble_members`

**Files:**
- Modify: `ai4science/llm/routing.py:21-41` (AGENT_CHAINS), add new function after `resolve_all`
- Test: `tests/test_ensemble_routing.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_routing.py
from ai4science.llm import routing


def test_no_opus_4_7_anywhere():
    for chain in routing.AGENT_CHAINS.values():
        assert ("anthropic", "claude-opus-4-7") not in chain
    # opus 4.8 is present in orchestration + checking
    assert ("anthropic", "claude-opus-4-8") in routing.AGENT_CHAINS["orchestration"]
    assert ("anthropic", "claude-opus-4-8") in routing.AGENT_CHAINS["checking"]


def test_ensemble_members_filters_by_availability(monkeypatch):
    monkeypatch.setattr(routing, "backend_available",
                        lambda b: b in ("anthropic", "gemini"))
    members = routing.ensemble_members("orchestration")
    backends = {b for b, _ in members}
    assert backends == {"anthropic", "gemini"}     # openai filtered out
    # order preserved from the chain, duplicates de-duped
    assert members == [m for m in routing.AGENT_CHAINS["orchestration"]
                       if m[0] in ("anthropic", "gemini")]


def test_ensemble_members_unknown_role():
    assert routing.ensemble_members("nope") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ensemble_routing.py -v`
Expected: FAIL — `test_no_opus_4_7_anywhere` fails (4.7 still present) and `ensemble_members` AttributeError.

- [ ] **Step 3: Edit `AGENT_CHAINS` (remove 4.7 → 4.8) and add `ensemble_members`**

In `ai4science/llm/routing.py`, change the `orchestration` chain first entry and the `checking` chain second entry:

```python
AGENT_CHAINS: Dict[str, List[Tuple[str, str]]] = {
    "orchestration": [
        ("anthropic", "claude-opus-4-8"),     # was opus-4-7; directive 2026-05-31
        ("anthropic", "claude-sonnet-4-6"),
        ("openai", "gpt-5.5"),
        ("gemini", "gemini-3.1-pro-preview"),
    ],
    "checking": [
        ("openai", "gpt-5.5"),
        ("anthropic", "claude-opus-4-8"),       # was opus-4-7
        ("gemini", "gemini-3.1-pro-preview"),
        ("deepseek", "deepseek-ai/deepseek-r1-0528-maas"),
    ],
    "fast": [
        ("gemini", "gemini-3.5-flash"),
        ("anthropic", "claude-haiku-4-5"),
        ("openai", "gpt-5.5-nano"),
        ("qwen", "qwen/qwen3-235b-a22b-instruct-2507-maas"),
    ],
}
```

Add this function at the end of the file:

```python
def ensemble_members(role: str) -> List[Tuple[str, str]]:
    """All reachable (backend, model) members of a role's pool, in chain order.

    Unlike resolve() (first-reachable single pick), the ensemble runs *every*
    reachable member. De-dupes while preserving order. Unknown role -> [].
    """
    chain = AGENT_CHAINS.get(role)
    if not chain:
        return []
    seen: set = set()
    out: List[Tuple[str, str]] = []
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
Expected: PASS (new tests pass; existing routing tests still green — if any existing test pinned `claude-opus-4-7`, update it to `claude-opus-4-8`).

- [ ] **Step 5: Commit**

```bash
git add ai4science/llm/routing.py tests/test_ensemble_routing.py
git commit -m "feat(routing): Opus 4.7->4.8 in chains; add ensemble_members()"
```

---

### Task 3: Ensemble config (read from user.json)

**Files:**
- Create: `ai4science/ensemble/config.py`
- Test: `tests/test_ensemble_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_config.py
from ai4science.ensemble import config
from ai4science import user


def test_defaults(monkeypatch):
    monkeypatch.setattr(user, "load", lambda: {})
    c = config.load()
    assert c.max_task_tokens == 2_000_000
    assert c.max_parallel_executors == 4
    assert abs(c.synthesis_epsilon - 0.05) < 1e-9
    assert c.test_command is None


def test_overrides_from_user_json(monkeypatch):
    monkeypatch.setattr(user, "load", lambda: {
        "ensemble": {
            "max_task_tokens": 500000,
            "max_parallel_executors": 2,
            "synthesis_epsilon": 0.1,
            "test_command": "pytest -q",
        }
    })
    c = config.load()
    assert c.max_task_tokens == 500000
    assert c.max_parallel_executors == 2
    assert c.test_command == "pytest -q"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ensemble_config.py -v`
Expected: FAIL — `ModuleNotFoundError: ai4science.ensemble.config`

- [ ] **Step 3: Implement config**

```python
# ai4science/ensemble/config.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ai4science import user

DEFAULTS = {
    "max_task_tokens": 2_000_000,
    "max_parallel_executors": 4,
    "synthesis_epsilon": 0.05,
    "test_command": None,
}


@dataclass
class EnsembleConfig:
    max_task_tokens: int
    max_parallel_executors: int
    synthesis_epsilon: float
    test_command: Optional[str]


def load() -> EnsembleConfig:
    raw = {}
    try:
        raw = (user.load() or {}).get("ensemble", {}) or {}
    except Exception:
        raw = {}
    merged = {**DEFAULTS, **{k: raw[k] for k in DEFAULTS if k in raw}}
    return EnsembleConfig(
        max_task_tokens=int(merged["max_task_tokens"]),
        max_parallel_executors=int(merged["max_parallel_executors"]),
        synthesis_epsilon=float(merged["synthesis_epsilon"]),
        test_command=merged["test_command"],
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ensemble_config.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/ensemble/config.py tests/test_ensemble_config.py
git commit -m "feat(ensemble): config loader with always-ensemble defaults"
```

---

### Task 4: Git worktree helpers

**Files:**
- Create: `ai4science/ensemble/worktree.py`
- Test: `tests/test_ensemble_worktree.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_worktree.py
import subprocess
from pathlib import Path
from ai4science.ensemble import worktree


def _init_repo(root: Path):
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    (root / "a.txt").write_text("hello\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"], check=True)


def test_add_edit_diff_remove(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    wt = worktree.add(repo, "cand-0")
    assert wt.exists()
    (wt / "a.txt").write_text("hello world\n")

    diff = worktree.diff(wt)
    assert "hello world" in diff and "a.txt" in diff

    changed = worktree.changed_files(wt)
    assert Path("a.txt") in changed

    worktree.remove(repo, wt)
    assert not wt.exists()


def test_apply_diff_to_main(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    wt = worktree.add(repo, "cand-0")
    (wt / "a.txt").write_text("changed\n")
    diff = worktree.diff(wt)
    worktree.remove(repo, wt)

    ok, msg = worktree.apply(repo, diff)
    assert ok, msg
    assert (repo / "a.txt").read_text() == "changed\n"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ensemble_worktree.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement worktree helpers**

```python
# ai4science/ensemble/worktree.py
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Tuple


def _git(repo: Path, *args: str, timeout: int = 120) -> Tuple[int, str]:
    p = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True, timeout=timeout,
    )
    return p.returncode, (p.stdout + p.stderr)


def add(repo: Path, label: str) -> Path:
    """Create a detached worktree of repo's HEAD under .git-ensemble/<label>."""
    wt = repo / ".git-ensemble" / label
    wt.parent.mkdir(parents=True, exist_ok=True)
    if wt.exists():
        remove(repo, wt)
    rc, out = _git(repo, "worktree", "add", "--detach", str(wt), "HEAD")
    if rc != 0:
        raise RuntimeError(f"git worktree add failed: {out}")
    return wt


def remove(repo: Path, wt: Path) -> None:
    _git(repo, "worktree", "remove", "--force", str(wt))
    # Defensive: prune in case the dir was already gone.
    _git(repo, "worktree", "prune")


def diff(wt: Path) -> str:
    """Unified diff of all changes (tracked + untracked) in the worktree."""
    _git(wt, "add", "-A")
    rc, out = _git(wt, "diff", "--cached")
    return out if rc == 0 else ""


def changed_files(wt: Path) -> List[Path]:
    _git(wt, "add", "-A")
    rc, out = _git(wt, "diff", "--cached", "--name-only")
    if rc != 0:
        return []
    return [Path(line) for line in out.splitlines() if line.strip()]


def apply(repo: Path, diff_text: str) -> Tuple[bool, str]:
    """Apply a unified diff (from a worktree) to the main repo work tree."""
    if not diff_text.strip():
        return True, "empty diff"
    p = subprocess.run(
        ["git", "-C", str(repo), "apply", "--whitespace=nowarn", "-"],
        input=diff_text, capture_output=True, text=True, timeout=120,
    )
    ok = p.returncode == 0
    return ok, (p.stdout + p.stderr) if not ok else "applied"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ensemble_worktree.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/ensemble/worktree.py tests/test_ensemble_worktree.py
git commit -m "feat(ensemble): git worktree add/diff/apply helpers"
```

---

### Task 5: Repo test-command detection + `check_result`

**Files:**
- Create: `ai4science/ensemble/checks.py`
- Test: `tests/test_ensemble_checks.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_checks.py
from pathlib import Path
from ai4science.ensemble import checks


def test_detect_pytest(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n")
    assert checks.detect_command(tmp_path) == "pytest -q"


def test_detect_npm(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}')
    assert checks.detect_command(tmp_path) == "npm test"


def test_detect_none(tmp_path):
    assert checks.detect_command(tmp_path) is None


def test_run_check_passes(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_x.py").write_text("def test_x():\n    assert True\n")
    res = checks.run(tmp_path, override=None)
    assert res["ran"] is True
    assert res["passed"] is True


def test_run_check_override_skips_detection(tmp_path):
    res = checks.run(tmp_path, override="python -c \"import sys; sys.exit(1)\"")
    assert res["ran"] is True
    assert res["passed"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ensemble_checks.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement checks**

```python
# ai4science/ensemble/checks.py
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Dict, Optional

CHECK_TIMEOUT_SECONDS = 600


def detect_command(workspace: Path) -> Optional[str]:
    """Best-effort detection of the repo's test command. None if unknown."""
    if (workspace / "pytest.ini").exists() or (workspace / "pyproject.toml").exists() \
            or list(workspace.glob("tests/test_*.py")) or list(workspace.glob("test_*.py")):
        return "pytest -q"
    pkg = workspace / "package.json"
    if pkg.exists():
        try:
            if "test" in (json.loads(pkg.read_text()).get("scripts") or {}):
                return "npm test"
        except Exception:
            pass
    if (workspace / "Cargo.toml").exists():
        return "cargo test"
    if (workspace / "go.mod").exists():
        return "go test ./..."
    return None


def run(workspace: Path, override: Optional[str]) -> Dict:
    """Run the (overridden or detected) test command. Never raises."""
    cmd = override or detect_command(workspace)
    if not cmd:
        return {"ran": False, "passed": False, "summary": "no test command detected"}
    try:
        p = subprocess.run(
            cmd, shell=True, cwd=str(workspace),
            capture_output=True, text=True, timeout=CHECK_TIMEOUT_SECONDS,
        )
    except Exception as exc:  # timeout / spawn failure
        return {"ran": True, "passed": False, "summary": f"check error: {exc}"}
    tail = (p.stdout + p.stderr).strip().splitlines()[-15:]
    return {
        "ran": True,
        "passed": p.returncode == 0,
        "summary": "\n".join(tail),
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ensemble_checks.py -v`
Expected: PASS (5 tests). (Requires `pytest` on PATH, which the dev env has.)

- [ ] **Step 5: Commit**

```bash
git add ai4science/ensemble/checks.py tests/test_ensemble_checks.py
git commit -m "feat(ensemble): repo test-command detection + check_result"
```

---

### Task 6: Pool resolution (executors + judges)

**Files:**
- Create: `ai4science/ensemble/pool.py`
- Test: `tests/test_ensemble_pool.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_pool.py
from ai4science.ensemble import pool
from ai4science.llm import routing


def test_executor_members_uses_orchestration(monkeypatch):
    monkeypatch.setattr(routing, "ensemble_members",
                        lambda role: [("anthropic", "claude-opus-4-8")] if role == "orchestration" else [])
    assert pool.executor_members() == [("anthropic", "claude-opus-4-8")]


def test_judge_members_union_checking_and_fast(monkeypatch):
    def fake(role):
        return {
            "checking": [("openai", "gpt-5.5"), ("anthropic", "claude-opus-4-8")],
            "fast": [("gemini", "gemini-3.5-flash"), ("anthropic", "claude-opus-4-8")],
        }.get(role, [])
    monkeypatch.setattr(routing, "ensemble_members", fake)
    members = pool.judge_members()
    # union, de-duped, checking first then fast
    assert members == [
        ("openai", "gpt-5.5"),
        ("anthropic", "claude-opus-4-8"),
        ("gemini", "gemini-3.5-flash"),
    ]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ensemble_pool.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement pool**

```python
# ai4science/ensemble/pool.py
from __future__ import annotations

from typing import List, Tuple

from ai4science.llm import routing

Member = Tuple[str, str]


def executor_members() -> List[Member]:
    """Reachable members of the executor (orchestration) pool."""
    return routing.ensemble_members("orchestration")


def judge_members() -> List[Member]:
    """Reachable judge panel = checking ∪ fast, de-duped, checking first."""
    seen: set = set()
    out: List[Member] = []
    for role in ("checking", "fast"):
        for m in routing.ensemble_members(role):
            if m not in seen:
                seen.add(m)
                out.append(m)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ensemble_pool.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/ensemble/pool.py tests/test_ensemble_pool.py
git commit -m "feat(ensemble): executor + judge pool resolution"
```

---

### Task 7: Judge panel (call a specific model, parse score, meter)

**Files:**
- Create: `ai4science/ensemble/panel.py`
- Test: `tests/test_ensemble_panel.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_panel.py
import json
from ai4science.ensemble import panel
from ai4science.ensemble.types import Candidate
from ai4science.llm import execute, routing


def _cands():
    return [
        Candidate(member=("anthropic", "claude-opus-4-8"), answer="A",
                  diff="diffA", check_result={"ran": True, "passed": False, "summary": ""}),
        Candidate(member=("openai", "gpt-5.5"), answer="B",
                  diff="diffB", check_result={"ran": True, "passed": True, "summary": "1 passed"}),
    ]


def test_parse_score_extracts_json():
    text = 'Here is my verdict:\n{"ranking": [1, 0], "scores": {"0": 0.3, "1": 0.8}, "rationale": "B passes"}'
    parsed = panel._parse_score(text, n=2)
    assert parsed["ranking"] == [1, 0]
    assert parsed["scores"][1] == 0.8


def test_run_panel_meters_and_collects(monkeypatch):
    # one judge, returns a fixed JSON verdict; usage metered
    monkeypatch.setattr(panel, "judge_members", lambda: [("openai", "gpt-5.5")])
    monkeypatch.setattr(routing, "_select_source",
                        lambda backend: ("wallet", "prov-1", "0xWALLET", 1.0))
    monkeypatch.setitem(
        execute._EXECUTORS, "openai",
        lambda model, prompt, reasoning, timeout: (
            json.dumps({"ranking": [1, 0], "scores": {"0": 0.3, "1": 0.8}, "rationale": "B"}),
            {"input": 100, "output": 20, "total": 120},
        ),
    )
    recorded = []
    monkeypatch.setattr(panel.ledger, "record", lambda **kw: recorded.append(kw))

    scores = panel.run("fix bug", _cands())
    assert len(scores) == 1
    assert scores[0].ranking == [1, 0]
    assert recorded and recorded[0]["wallet"] == "0xWALLET"
    assert recorded[0]["model"] == "gpt-5.5"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ensemble_panel.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement panel**

```python
# ai4science/ensemble/panel.py
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

from ai4science.ensemble.pool import judge_members
from ai4science.ensemble.types import Candidate, JudgeScore, Member
from ai4science.llm import execute, ledger, pricing, routing

JUDGE_TIMEOUT_SECONDS = 180

_RUBRIC = """You are one judge on a panel scoring candidate solutions to a task.

TASK:
{task}

Score every candidate from 0.0 (worst) to 1.0 (best) on correctness first
(does its diff and test result actually solve the task?), then quality.
A candidate whose tests FAILED cannot outscore one whose tests PASSED unless
the passing one is clearly off-task.

CANDIDATES:
{candidates}

Respond with ONLY a JSON object, no prose:
{{"ranking": [best_index, ..., worst_index],
  "scores": {{"<index>": <float 0..1>, ...}},
  "rationale": "<one sentence>"}}"""


def _render_candidates(cands: List[Candidate]) -> str:
    blocks = []
    for i, c in enumerate(cands):
        chk = c.check_result or {}
        blocks.append(
            f"[{i}] model={c.member[1]}\n"
            f"  tests_ran={chk.get('ran')} tests_passed={chk.get('passed')}\n"
            f"  test_summary: {chk.get('summary', '')[:500]}\n"
            f"  answer: {c.answer[:1000]}\n"
            f"  diff:\n{(c.diff or '')[:4000]}"
        )
    return "\n\n".join(blocks)


def _parse_score(text: str, n: int) -> Optional[Dict]:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
    except Exception:
        return None
    ranking = [int(x) for x in obj.get("ranking", []) if 0 <= int(x) < n]
    scores = {int(k): float(v) for k, v in (obj.get("scores") or {}).items()
              if 0 <= int(k) < n}
    if not ranking and not scores:
        return None
    return {"ranking": ranking, "scores": scores,
            "rationale": str(obj.get("rationale", ""))}


def _score_one(judge: Member, task: str, cands: List[Candidate]) -> JudgeScore:
    backend, model = judge
    reasoning = routing.AGENT_REASONING.get("checking", "high")
    prompt = _RUBRIC.format(task=task, candidates=_render_candidates(cands))
    executor = execute._EXECUTORS.get(backend)
    if executor is None:
        return JudgeScore(judge, [], {}, "", error=f"no executor for {backend}")
    try:
        text, usage = executor(model, prompt, reasoning, JUDGE_TIMEOUT_SECONDS)
    except Exception as exc:
        return JudgeScore(judge, [], {}, "", error=str(exc))

    # meter the judge call
    try:
        source, provider_id, wallet, mult = routing._select_source(backend)
        cost = pricing.price_call(model, usage, price_multiplier=mult)
        ledger.record(agent="ensemble-judge", backend=backend, model=model,
                      wallet=wallet, usage=usage, cost=cost)
    except Exception:
        pass

    parsed = _parse_score(text, len(cands))
    if parsed is None:
        return JudgeScore(judge, [], {}, text[:200], error="unparseable verdict")
    return JudgeScore(judge, parsed["ranking"], parsed["scores"], parsed["rationale"])


def run(task: str, cands: List[Candidate]) -> List[JudgeScore]:
    judges = judge_members()
    if not judges:
        return []
    with ThreadPoolExecutor(max_workers=min(8, len(judges))) as ex:
        return list(ex.map(lambda j: _score_one(j, task, cands), judges))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ensemble_panel.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/ensemble/panel.py tests/test_ensemble_panel.py
git commit -m "feat(ensemble): judge panel scoring + per-call PWM metering"
```

---

### Task 8: Selection (aggregate, winner, synthesis trigger)

**Files:**
- Create: `ai4science/ensemble/select.py`
- Test: `tests/test_ensemble_select.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_select.py
from ai4science.ensemble import select
from ai4science.ensemble.types import JudgeScore


def test_aggregate_picks_highest_mean():
    scores = [
        JudgeScore(("openai", "gpt-5.5"), [1, 0], {0: 0.2, 1: 0.9}, ""),
        JudgeScore(("gemini", "gemini-3.5-flash"), [1, 0], {0: 0.3, 1: 0.8}, ""),
    ]
    sel = select.aggregate(scores, n=2, epsilon=0.05, senior_member=("anthropic", "claude-opus-4-8"))
    assert sel.winner == 1
    assert sel.synthesized is False        # 0.85 vs 0.25 -> not close


def test_synthesis_triggers_when_close():
    scores = [
        JudgeScore(("openai", "gpt-5.5"), [0, 1], {0: 0.81, 1: 0.80}, ""),
    ]
    sel = select.aggregate(scores, n=2, epsilon=0.05, senior_member=("anthropic", "claude-opus-4-8"))
    assert sel.synthesized is True


def test_tiebreak_prefers_senior_judges_pick():
    # exact tie on mean; senior judge ranked candidate 1 first
    scores = [
        JudgeScore(("openai", "gpt-5.5"), [0, 1], {0: 0.5, 1: 0.5}, ""),
        JudgeScore(("anthropic", "claude-opus-4-8"), [1, 0], {0: 0.5, 1: 0.5}, ""),
    ]
    sel = select.aggregate(scores, n=2, epsilon=0.0, senior_member=("anthropic", "claude-opus-4-8"))
    assert sel.winner == 1


def test_empty_scores_returns_zero_winner():
    sel = select.aggregate([], n=3, epsilon=0.05, senior_member=("anthropic", "claude-opus-4-8"))
    assert sel.winner == 0
    assert "no judge" in sel.rationale.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ensemble_select.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement select**

```python
# ai4science/ensemble/select.py
from __future__ import annotations

from typing import Dict, List

from ai4science.ensemble.types import JudgeScore, Member, Selection


def _mean_scores(scores: List[JudgeScore], n: int) -> Dict[int, float]:
    totals = {i: 0.0 for i in range(n)}
    counts = {i: 0 for i in range(n)}
    for js in scores:
        for i, v in js.scores.items():
            if 0 <= i < n:
                totals[i] += v
                counts[i] += 1
    return {i: (totals[i] / counts[i] if counts[i] else 0.0) for i in range(n)}


def aggregate(scores: List[JudgeScore], n: int, epsilon: float,
              senior_member: Member) -> Selection:
    if not scores or n == 0:
        return Selection(winner=0, ranking=list(range(n)),
                         rationale="no judge scores; defaulted to candidate 0")

    means = _mean_scores(scores, n)
    ranking = sorted(range(n), key=lambda i: means[i], reverse=True)
    top = ranking[0]

    # tie-break by the senior judge's top pick, if any judge is the senior model
    if n >= 2 and abs(means[ranking[0]] - means[ranking[1]]) < 1e-9:
        for js in scores:
            if js.judge == senior_member and js.ranking:
                top = js.ranking[0]
                ranking = [top] + [i for i in ranking if i != top]
                break

    synthesized = (n >= 2 and abs(means[ranking[0]] - means[ranking[1]]) <= epsilon)
    rationale = (f"winner={top} mean={means[top]:.3f}; "
                 f"runner-up mean={means[ranking[1]]:.3f}" if n >= 2
                 else f"winner={top} mean={means[top]:.3f}")
    return Selection(winner=top, ranking=ranking, rationale=rationale,
                     synthesized=synthesized)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ensemble_select.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/ensemble/select.py tests/test_ensemble_select.py
git commit -m "feat(ensemble): score aggregation, winner, synthesis trigger"
```

---

### Task 9: Runner (executors in worktrees → candidates)

**Files:**
- Create: `ai4science/ensemble/runner.py`
- Test: `tests/test_ensemble_runner.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_ensemble_runner.py
import subprocess
from pathlib import Path
from ai4science.agents.base import AgentResult
from ai4science.ensemble import runner


def _init_repo(root: Path):
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    (root / "a.txt").write_text("v0\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"], check=True)


class _StubAgent:
    """Writes a member-specific file into the worktree, returns ok."""
    def __init__(self, member):
        self.member = member

    def run_task(self, prompt, workspace, context_files):
        (workspace / "a.txt").write_text(f"edited by {self.member[1]}\n")
        return AgentResult(status="ok", message=f"{self.member[1]} done",
                           changed_files=[Path("a.txt")])


def test_runner_produces_one_candidate_per_member(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    members = [("anthropic", "claude-opus-4-8"), ("openai", "gpt-5.5")]
    monkeypatch.setattr(runner, "executor_members", lambda: members)
    monkeypatch.setattr(runner, "_agent_for", lambda member: _StubAgent(member))
    # skip real test runs
    monkeypatch.setattr(runner.checks, "run",
                        lambda ws, override: {"ran": False, "passed": False, "summary": ""})

    cands = runner.run("edit a.txt", repo, max_parallel=2, test_override=None)
    assert len(cands) == 2
    answers = sorted(c.answer for c in cands)
    assert answers == ["claude-opus-4-8 done", "gpt-5.5 done"]
    for c in cands:
        assert "edited by" in (c.diff or "")
    # all worktrees cleaned up
    assert not (repo / ".git-ensemble").exists() or not any((repo / ".git-ensemble").iterdir())


def test_runner_drops_failed_executor(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    class _Boom:
        def run_task(self, prompt, workspace, context_files):
            raise RuntimeError("kaboom")

    members = [("anthropic", "claude-opus-4-8"), ("openai", "gpt-5.5")]
    monkeypatch.setattr(runner, "executor_members", lambda: members)
    monkeypatch.setattr(runner, "_agent_for",
                        lambda m: _Boom() if m[0] == "openai" else _StubAgent(m))
    monkeypatch.setattr(runner.checks, "run",
                        lambda ws, override: {"ran": False, "passed": False, "summary": ""})

    cands = runner.run("x", repo, max_parallel=2, test_override=None)
    assert len(cands) == 1
    assert cands[0].member == ("anthropic", "claude-opus-4-8")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ensemble_runner.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement runner**

```python
# ai4science/ensemble/runner.py
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import List, Optional

from ai4science.agents import get_agent
from ai4science.ensemble import checks, worktree
from ai4science.ensemble.pool import executor_members
from ai4science.ensemble.types import Candidate, Member

# backend -> the BaseAgent provider name that drives that brand's loop.
# Plan 1: only anthropic has a real agentic driver; others fall back to claude
# until Plan 2 ships CodexAgent(agentic) + GeminiAgent. Tests monkeypatch _agent_for.
_BACKEND_AGENT = {
    "anthropic": "claude",
    "openai": "codex",
    "gemini": "claude",     # placeholder until Plan 2's GeminiAgent
    "deepseek": "claude",
    "qwen": "claude",
}


def _agent_for(member: Member):
    backend, _model = member
    return get_agent(_BACKEND_AGENT.get(backend, "claude"), read_only=False)


def _run_member(member: Member, prompt: str, repo: Path,
                idx: int, test_override: Optional[str]) -> Optional[Candidate]:
    label = f"cand-{idx}-{member[0]}"
    wt = None
    try:
        wt = worktree.add(repo, label)
        agent = _agent_for(member)
        result = agent.run_task(prompt, wt, [])
        if getattr(result, "status", "error") != "ok":
            return None
        diff = worktree.diff(wt)
        changed = worktree.changed_files(wt)
        check = checks.run(wt, override=test_override)
        return Candidate(member=member, answer=result.message, diff=diff,
                         changed_files=changed, check_result=check, worktree=None)
    except Exception:
        return None
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
            list(enumerate(members)),
        ))
    return [c for c in results if c is not None]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ensemble_runner.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add ai4science/ensemble/runner.py tests/test_ensemble_runner.py
git commit -m "feat(ensemble): worktree-isolated executor runner"
```

---

### Task 10: Pipeline orchestration + `ensemble-run` CLI

**Files:**
- Create: `ai4science/ensemble/pipeline.py`
- Modify: `ai4science/cli.py` (register `ensemble-run` command near the other `app.command()` single commands)
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
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    (root / "a.txt").write_text("v0\n")
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-q", "-m", "init"], check=True)


def test_pipeline_applies_winner_diff(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    cands = [
        Candidate(member=("anthropic", "claude-opus-4-8"), answer="A",
                  diff=("diff --git a/a.txt b/a.txt\n--- a/a.txt\n+++ b/a.txt\n"
                        "@@ -1 +1 @@\n-v0\n+winner\n"),
                  check_result={"ran": True, "passed": True, "summary": ""}),
    ]
    monkeypatch.setattr(pipeline, "_run_executors", lambda *a, **k: cands)
    monkeypatch.setattr(pipeline.panel, "run",
                        lambda task, cs: [JudgeScore(("openai", "gpt-5.5"), [0], {0: 0.9}, "best")])

    out = pipeline.run("make it say winner", repo)
    assert out["winner_model"] == "claude-opus-4-8"
    assert out["applied"] is True
    assert (repo / "a.txt").read_text() == "winner\n"


def test_pipeline_no_candidates(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)
    monkeypatch.setattr(pipeline, "_run_executors", lambda *a, **k: [])
    out = pipeline.run("x", repo)
    assert out["applied"] is False
    assert "no candidates" in out["error"].lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_ensemble_pipeline.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement pipeline**

```python
# ai4science/ensemble/pipeline.py
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from ai4science.ensemble import config as cfg
from ai4science.ensemble import panel, runner, select, worktree
from ai4science.ensemble.types import Candidate

SENIOR_JUDGE = ("anthropic", "claude-opus-4-8")


def _run_executors(prompt: str, repo: Path, max_parallel: int,
                   test_override: Optional[str]) -> List[Candidate]:
    return runner.run(prompt, repo, max_parallel=max_parallel,
                      test_override=test_override)


def run(task: str, repo: Path) -> Dict:
    """Full common-mode ensemble for one task. Returns a result summary dict."""
    c = cfg.load()
    cands = _run_executors(task, repo, c.max_parallel_executors, c.test_command)
    if not cands:
        return {"applied": False, "error": "no candidates produced",
                "winner_model": None, "candidates": 0}

    if len(cands) == 1:
        sel_winner = 0
        ranking = [0]
        rationale = "single reachable executor; applied directly"
        synthesized = False
        scores = []
    else:
        scores = panel.run(task, cands)
        sel = select.aggregate(scores, n=len(cands),
                               epsilon=c.synthesis_epsilon,
                               senior_member=SENIOR_JUDGE)
        sel_winner, ranking, rationale, synthesized = (
            sel.winner, sel.ranking, sel.rationale, sel.synthesized)

    winner = cands[sel_winner]
    applied, msg = worktree.apply(repo, winner.diff or "")
    return {
        "applied": applied,
        "apply_message": msg,
        "winner_model": winner.member[1],
        "winner_answer": winner.answer,
        "ranking": [cands[i].member[1] for i in ranking],
        "rationale": rationale,
        "synthesized": synthesized,
        "candidates": len(cands),
        "judges": len(scores),
        "error": None if applied else f"diff apply failed: {msg}",
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_ensemble_pipeline.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Register the `ensemble-run` CLI command**

In `ai4science/cli.py`, near the other single-command registrations (after `app.command()(status)` / the block around lines 81–112), add:

```python
@app.command(name="ensemble-run")
def ensemble_run(
    task: str = typer.Argument(..., help="The task to run through the common-mode ensemble"),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Repo root (must be a git work tree)"),
) -> None:
    """Run one task through the multi-brand executor-ensemble → judge-panel."""
    from ai4science.ensemble import pipeline
    import json as _json
    out = pipeline.run(task, workspace.resolve())
    typer.echo(_json.dumps(out, indent=2))
    raise typer.Exit(0 if out.get("applied") else 2)
```

- [ ] **Step 6: Add a CLI smoke test**

```python
# append to tests/test_ensemble_pipeline.py
from typer.testing import CliRunner
from ai4science.cli import app


def test_cli_ensemble_run_invokes_pipeline(monkeypatch):
    from ai4science.ensemble import pipeline as pl
    monkeypatch.setattr(pl, "run", lambda task, repo: {
        "applied": True, "winner_model": "claude-opus-4-8", "candidates": 2})
    res = CliRunner().invoke(app, ["ensemble-run", "do the thing"])
    assert res.exit_code == 0
    assert "claude-opus-4-8" in res.stdout
```

- [ ] **Step 7: Run all ensemble tests**

Run: `python -m pytest tests/test_ensemble_pipeline.py -v`
Expected: PASS (3 tests incl. CLI smoke)

- [ ] **Step 8: Commit**

```bash
git add ai4science/ensemble/pipeline.py ai4science/cli.py tests/test_ensemble_pipeline.py
git commit -m "feat(ensemble): pipeline orchestration + ensemble-run CLI"
```

---

### Task 11: Full suite green + docs note

**Files:**
- Modify: `docs/CLAUDE_CODE_PARITY.md` (add a short "common mode is now an ensemble" note)
- Test: whole suite

- [ ] **Step 1: Run the entire test suite**

Run: `python -m pytest -q`
Expected: PASS — all existing tests plus the new `tests/test_ensemble_*.py`. If an existing routing/cli test pinned `claude-opus-4-7`, update it to `claude-opus-4-8` (Task 2) and re-run.

- [ ] **Step 2: Add the parity note**

Append to `docs/CLAUDE_CODE_PARITY.md`:

```markdown
## Common mode is a multi-brand ensemble (2026-05-31)

Common mode no longer runs a single model. Each task is attempted in parallel by
the executor pool (Opus 4.8, Sonnet 4.6, GPT-5.5, Gemini 3.1 Pro), scored by a
judge panel (checking ∪ fast), and the winning diff is applied. See
`docs/superpowers/specs/2026-05-31-common-mode-multibrand-ensemble-design.md`.
Core pipeline lands in `ai4science/ensemble/`; brand agentic drivers (Codex,
Gemini) and REPL wiring follow in Plans 2 and 3.
```

- [ ] **Step 3: Commit**

```bash
git add docs/CLAUDE_CODE_PARITY.md
git commit -m "docs(parity): note common mode is now a multi-brand ensemble"
```

---

## Self-review

- **Spec coverage:** executor-ensemble (Task 9), judge-panel checking∪fast (Tasks 6,7), select+synthesis (Task 8), worktree isolation (Task 4), check_result objective signal (Task 5), Opus 4.7→4.8 (Task 2), config/ceiling/concurrency (Task 3), PWM accounting for judges (Task 7), runnable entry (Task 10). Deferred-by-design and called out: vendor agentic drivers (Plan 2), REPL wiring (Plan 3), executor token metering (Plan 2), per-task token-ceiling enforcement mid-run (the `max_task_tokens` value is loaded in Task 3 and surfaced to the pipeline; hard mid-run abort is wired in Plan 2 alongside executor usage, since Plan 1 executors don't surface live token counts — noted, not a silent gap).
- **Placeholder scan:** none — every step has complete code/commands.
- **Type consistency:** `Candidate`/`JudgeScore`/`Selection` fields are used identically across `panel.py`, `select.py`, `runner.py`, `pipeline.py`; `ensemble_members(role)` and `_select_source(backend) -> (source, provider_id, wallet, mult)` match the real signatures from `routing.py`; `execute._EXECUTORS[backend](model, prompt, reasoning, timeout) -> (text, usage)` matches `execute.py`; `ledger.record(agent, backend, model, wallet, usage, cost)` matches `ledger.py`; `pricing.price_call(model, usage, price_multiplier)` matches `pricing.py`; `BaseAgent.run_task(prompt, workspace, context_files) -> AgentResult(status, message, changed_files, ...)` matches `agents/base.py`.

## Known limitations (carried to Plan 2/3)

1. Until Plan 2, only `anthropic` has a real agentic driver; `_BACKEND_AGENT` maps other backends to `claude`/`codex` placeholders, so the "ensemble" is genuinely multi-model only once Codex(agentic) + GeminiAgent land. The pool/panel/select machinery is fully exercised now via stubs.
2. Executor token usage is not yet metered (judges are). Mid-run token-ceiling abort lands with executor usage in Plan 2.
3. REPL (`chat.py`) still uses the single Claude-SDK driver; `ensemble-run` is the Plan-1 user entry. REPL wiring is Plan 3.
