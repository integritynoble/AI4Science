# Computational-Imaging Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the `computational-imaging` agent into a real CASSI domain expert with a 4-tool `computational-imaging` capability bundle: `cassi_solutions` (all registered imaging solutions across mainnet+testnet, marked by chain), `cassi_forward_check` (local physics residual), `cassi_dispatch` (run a solver on the sub-GPU server, cost-guarded), `cassi_result` (poll + judge → PSNR/score_q).

**Architecture:** A new `ai4science/harness/cassi_tools.py` holds the four tools + helpers; the `computational-imaging` capability bundle (in `capabilities.py`) returns `cassi_tools()`. The agent's spec lists the bundle, so the framework wires it automatically — the moat (common can't reach these) is structural. GPU dispatch reuses `ai4science/compute/` (`dispatch_job`/`job_state`/`read_result`/`get_provider`); local physics reuses `ai4science/judge/cassi/forward.py` + `judge_cassi`. PWM cost is a previewed stub (recipient = third-founder address); no tokens move.

**Tech Stack:** Python 3, stdlib + numpy (2.4 present), pytest. No new third-party deps.

**Spec:** `docs/superpowers/specs/2026-06-06-computational-imaging-agent-design.md` (read it).

**Confirmed signatures (verified):**
- `ai4science/compute/dispatch.py`: `dispatch_job(*, provider, workspace: Path, benchmark_id="", solver_code_path="code/") -> Job` (Job has `.job_id`); `job_state(endpoint_path: Path, job_id) -> dict` with `state` in `{"unknown","acked","completed",...}` (**done == "completed"**); `read_result(endpoint_path, job_id) -> Optional[dict]`.
- `ai4science/compute/registry.py`: `get_provider(provider_id, path=None) -> Optional[ComputeProvider]`; `load_registry(path=None) -> List[ComputeProvider]`; `ComputeProvider` has `.provider_id`, `.endpoint_path`, `.wallet_address`.
- `ai4science/judge/cassi/forward.py`: `cassi_forward(x:(H,W,C), mask:(H,W)) -> y:(H, W+C-1)`.
- `ai4science/judge/cassi/judge_cassi.py`: `judge_cassi(submission: Path, benchmark=None) -> dict`.
- `ai4science/harness/transport.py`: `get_json(url, timeout=60) -> dict|list`.

**Run tests:** `PYTHONPATH=$(pwd) python3 -m pytest <path> -v` from the repo root (`python3`). Baseline on `main`: `410 passed, 4 skipped, 2 failed` (the 2 = pre-existing `test_chat.py::test_list_sessions_*`, `claude_agent_sdk` absent; leave them).

**Branch:** create `feat/ci-agent` off `main` before Task 1.

---

## File Structure

| File | Responsibility |
|---|---|
| `ai4science/harness/cassi_tools.py` | helpers (`_contained`, `_resolve_provider`, `_solution_cost`, `_chain_bases`, `cassi_solutions_multichain`) + 4 tool builders + `cassi_tools()` |
| `ai4science/harness/agents/capabilities.py` | (modify) register the `computational-imaging` bundle |
| `ai4science/harness/agents/specs/computational_imaging.py` | (modify) enrich the expert prompt |
| `docs/CLAUDE_CODE_PARITY.md` | (modify) "Specific domain agents" note |
| `tests/test_harness_cassi_*.py` | unit tests per tool |

`cassi_tools()` grows one tool per task; the integration test (Task 6) asserts all four.

---

## Task 1: Scaffold `cassi_tools.py` + `cassi_forward_check`

**Files:**
- Create: `ai4science/harness/cassi_tools.py`
- Test: `tests/test_harness_cassi_forward.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_cassi_forward.py
import numpy as np
from ai4science.harness import cassi_tools
from ai4science.harness.cassi_tools import cassi_tools as build_cassi_tools
from ai4science.judge.cassi.forward import cassi_forward


def _tools():
    return {t.name: t for t in build_cassi_tools()}


def _make_arrays(tmp_path, perturb=False):
    rng = np.random.default_rng(0)
    x = rng.random((4, 4, 3))
    mask = (rng.random((4, 4)) > 0.5).astype(float)
    y = cassi_forward(x, mask)
    if perturb:
        y = y + 1.0
    np.save(tmp_path / "recon.npy", x)
    np.save(tmp_path / "mask.npy", mask)
    np.save(tmp_path / "meas.npy", y)


def test_forward_check_consistent(tmp_path):
    _make_arrays(tmp_path, perturb=False)
    out = _tools()["cassi_forward_check"].func(
        tmp_path, recon="recon.npy", mask="mask.npy", measurement="meas.npy")
    assert "consistent" in out.lower()


def test_forward_check_inconsistent(tmp_path):
    _make_arrays(tmp_path, perturb=True)
    out = _tools()["cassi_forward_check"].func(
        tmp_path, recon="recon.npy", mask="mask.npy", measurement="meas.npy")
    assert "inconsistent" in out.lower() or "marginal" in out.lower()


def test_forward_check_path_escape(tmp_path):
    out = _tools()["cassi_forward_check"].func(
        tmp_path, recon="../x.npy", mask="mask.npy", measurement="meas.npy")
    assert "[cassi error]" in out


def test_forward_check_tool_non_mutating():
    assert _tools()["cassi_forward_check"].mutating is False
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: ... cassi_tools`).

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_cassi_forward.py -v`

- [ ] **Step 3: Create `ai4science/harness/cassi_tools.py`**

```python
from __future__ import annotations

from pathlib import Path
from typing import List

from ai4science.harness.tools.base import Tool

# Genesis CASSI solutions are authored by the third founder; users' PWM for using
# them is paid to this address (charging itself is deferred to the economics layer).
GENESIS_SOLUTION_PROVIDER = "0xde81b29E42F95C92c9A4Dc78882d0F05D2C81A29"


class CassiError(Exception):
    pass


def _contained(workspace: Path, rel: str) -> Path:
    target = (Path(workspace) / rel).resolve()
    try:
        target.relative_to(Path(workspace).resolve())
    except ValueError:
        raise CassiError(f"path escapes the workspace: {rel}")
    return target


def _forward_check_tool() -> Tool:
    def _check(workspace, *, recon: str, mask: str, measurement: str) -> str:
        try:
            import numpy as np
            from ai4science.judge.cassi.forward import cassi_forward
            x = np.load(_contained(Path(workspace), recon))
            m = np.load(_contained(Path(workspace), mask))
            y = np.load(_contained(Path(workspace), measurement))
            y_hat = cassi_forward(x, m)
            if y_hat.shape != y.shape:
                return (f"[cassi error] measurement shape {y.shape} != forward output "
                        f"{y_hat.shape}")
            r = float(np.linalg.norm(y_hat - y) / (np.linalg.norm(y) + 1e-12))
            hint = "consistent" if r < 0.05 else ("marginal" if r < 0.2 else "inconsistent")
            return f"forward residual ||Φx - y|| / ||y|| = {r:.4f} ({hint})"
        except CassiError as exc:
            return f"[cassi error] {exc}"
        except Exception as exc:
            return f"[cassi error] {exc}"

    return Tool(
        name="cassi_forward_check",
        description=("Local CASSI physics sanity check: relative forward residual "
                     "||Φx - y|| / ||y|| for a reconstruction. Args are workspace "
                     ".npy paths: recon (H,W,C), mask (H,W), measurement (H,W+C-1)."),
        parameters={"type": "object", "properties": {
            "recon": {"type": "string"}, "mask": {"type": "string"},
            "measurement": {"type": "string"}},
            "required": ["recon", "mask", "measurement"]},
        func=_check, mutating=False)


def cassi_tools() -> List[Tool]:
    return [_forward_check_tool()]
```

- [ ] **Step 4: Run → PASS** (4 passed).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/cassi_tools.py tests/test_harness_cassi_forward.py
git commit -m "feat(cassi): cassi_forward_check tool (local physics residual)"
```

---

## Task 2: `cassi_solutions` (all imaging solutions, both chains, marked)

**Files:**
- Modify: `ai4science/harness/cassi_tools.py`
- Test: `tests/test_harness_cassi_solutions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_cassi_solutions.py
from ai4science.harness import cassi_tools
from ai4science.harness.cassi_tools import cassi_tools as build_cassi_tools


def _tools():
    return {t.name: t for t in build_cassi_tools()}


def _fake_get_json(mapping):
    def _g(url, timeout=60):
        for key, val in mapping.items():
            if url.endswith(key):
                return val
        raise RuntimeError(f"unmocked url {url}")
    return _g


# canned explorer data: one imaging benchmark with a reference solution
_BENCHMARKS = {"genesis": [{"benchmark_id": "L3-003", "title": "CASSI Mismatch Suite",
                            "category": "computational-imaging"},
                           {"benchmark_id": "L9-001", "title": "Unrelated", "category": "x"}]}
_LEADERBOARD = {"benchmark_id": "L3-003",
                "reference_advanced": {"label": "MST-L", "score_q": 0.95, "psnr_db": 35.3}}


def test_solutions_testnet_only_marks_chain(tmp_path, monkeypatch):
    monkeypatch.delenv("PWM_EXPLORER_BASE_MAINNET", raising=False)
    monkeypatch.setattr(cassi_tools.transport, "get_json",
                        _fake_get_json({"/benchmarks": _BENCHMARKS,
                                        "/leaderboard/L3-003": _LEADERBOARD}))
    out = _tools()["cassi_solutions"].func(tmp_path, benchmark="")
    assert "[testnet]" in out and "MST-L" in out and "L3-003" in out
    assert "[mainnet]" not in out
    assert "mainnet: not configured" in out


def test_solutions_both_chains(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_EXPLORER_BASE_MAINNET", "https://mainnet.example/api")
    monkeypatch.setattr(cassi_tools.transport, "get_json",
                        _fake_get_json({"/benchmarks": _BENCHMARKS,
                                        "/leaderboard/L3-003": _LEADERBOARD}))
    out = _tools()["cassi_solutions"].func(tmp_path, benchmark="L3-003")
    assert "[mainnet]" in out and "[testnet]" in out


def test_solutions_one_chain_unavailable(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_EXPLORER_BASE_MAINNET", "https://mainnet.example/api")
    def _g(url, timeout=60):
        if url.startswith("https://mainnet.example"):
            raise RuntimeError("down")
        if url.endswith("/leaderboard/L3-003"):
            return _LEADERBOARD
        raise RuntimeError("unmocked")
    monkeypatch.setattr(cassi_tools.transport, "get_json", _g)
    out = _tools()["cassi_solutions"].func(tmp_path, benchmark="L3-003")
    assert "[testnet]" in out and "unavailable" in out.lower()
```

- [ ] **Step 2: Run → FAIL** (`KeyError: 'cassi_solutions'`).

- [ ] **Step 3: Add to `cassi_tools.py`**

Add the import at the top (with the others):

```python
import os
from ai4science.harness import transport
```

Add helpers + the tool builder (place above `cassi_tools()`):

```python
_IMAGING_KEYWORDS = ("cassi", "spectral", "imaging", "hyperspectral", "snapshot")


def _chain_bases():
    """[(label, base_url)] for each configured chain + whether mainnet is set."""
    mn = os.environ.get("PWM_EXPLORER_BASE_MAINNET", "").rstrip("/")
    tn = os.environ.get("PWM_EXPLORER_BASE_TESTNET",
                        os.environ.get("PWM_EXPLORER_BASE",
                                       "https://explorer.physicsworldmodel.org/api")).rstrip("/")
    bases = []
    if mn:
        bases.append(("mainnet", mn))
    bases.append(("testnet", tn))
    return bases, bool(mn)


def _flatten_solutions(ld) -> list:
    out = []
    if isinstance(ld, dict):
        for key in ("reference", "reference_advanced"):
            s = ld.get(key)
            if isinstance(s, dict):
                out.append({**s, "_kind": key})
        for k in ("solutions", "submissions", "entries", "ranks"):
            v = ld.get(k)
            if isinstance(v, list):
                out.extend(x for x in v if isinstance(x, dict))
    return out


def _imaging_benchmark_ids(bdata) -> list:
    items = bdata.get("genesis") or bdata.get("benchmarks") or [] if isinstance(bdata, dict) else bdata
    ids = []
    for b in (items or []):
        if not isinstance(b, dict):
            continue
        hay = " ".join(str(b.get(k, "")) for k in ("benchmark_id", "title", "category")).lower()
        if any(kw in hay for kw in _IMAGING_KEYWORDS):
            bid = b.get("benchmark_id") or b.get("id")
            if bid:
                ids.append(bid)
    return ids


def cassi_solutions_multichain(benchmark: str = ""):
    """(solutions, notes). Each solution dict is tagged chain="mainnet"|"testnet"."""
    bases, has_mainnet = _chain_bases()
    sols, notes = [], []
    for label, base in bases:
        try:
            bids = [benchmark] if benchmark else _imaging_benchmark_ids(
                transport.get_json(f"{base}/benchmarks"))
            for bid in bids:
                ld = transport.get_json(f"{base}/leaderboard/{bid}")
                for s in _flatten_solutions(ld):
                    sols.append({**s, "benchmark_id": bid, "chain": label})
        except Exception as exc:
            notes.append(f"{label}: unavailable ({exc})")
    if not has_mainnet:
        notes.append("mainnet: not configured (set PWM_EXPLORER_BASE_MAINNET)")
    return sols, notes


def _solutions_tool() -> Tool:
    def _list(workspace, *, benchmark: str = "") -> str:
        try:
            sols, notes = cassi_solutions_multichain(benchmark)
            lines = []
            for s in sols:
                label = s.get("label") or s.get("name") or s.get("_kind") or "?"
                lines.append(f"[{s['chain']}] {s.get('benchmark_id','?')} {label} "
                             f"score_q={s.get('score_q')} psnr={s.get('psnr_db')}")
            body = "\n".join(lines) if lines else "(no registered imaging solutions found)"
            if notes:
                body += "\n" + "\n".join(notes)
            return body[:20000]
        except Exception as exc:
            return f"[cassi error] {exc}"

    return Tool(
        name="cassi_solutions",
        description=("List ALL registered computational-imaging solutions across "
                     "mainnet and testnet, each marked by chain. Optional benchmark "
                     "id narrows to one leaderboard; empty lists all imaging benchmarks."),
        parameters={"type": "object", "properties": {
            "benchmark": {"type": "string"}}, "required": []},
        func=_list, mutating=False)
```

Update `cassi_tools()`:

```python
def cassi_tools() -> List[Tool]:
    return [_solutions_tool(), _forward_check_tool()]
```

- [ ] **Step 4: Run → PASS** (3 passed). Re-run Task 1 test to confirm no regression.

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_cassi_solutions.py tests/test_harness_cassi_forward.py -v`

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/cassi_tools.py tests/test_harness_cassi_solutions.py
git commit -m "feat(cassi): cassi_solutions — all imaging solutions across mainnet+testnet, marked"
```

---

## Task 3: `cassi_dispatch` (sub-GPU, cost-guarded, third-founder recipient)

**Files:**
- Modify: `ai4science/harness/cassi_tools.py`
- Test: `tests/test_harness_cassi_dispatch.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_cassi_dispatch.py
from ai4science.harness import cassi_tools
from ai4science.harness.cassi_tools import (
    cassi_tools as build_cassi_tools, _solution_cost, GENESIS_SOLUTION_PROVIDER)


class _Prov:
    provider_id = "subgpu"
    endpoint_path = "/tmp/subgpu_inbox"
    wallet_address = "0xCAFE"


def _tools():
    return {t.name: t for t in build_cassi_tools()}


def test_solution_cost_own_vs_registered():
    cost, recipient, prov = _solution_cost("")
    assert recipient == "you"
    cost, recipient, prov = _solution_cost("L3-003-sol-1")
    assert recipient == GENESIS_SOLUTION_PROVIDER and "L3-003-sol-1" in prov


def test_dispatch_preview_no_spend(tmp_path, monkeypatch):
    (tmp_path / "code").mkdir()
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: _Prov())
    called = {"n": 0}
    monkeypatch.setattr(cassi_tools, "dispatch_job",
                        lambda **k: (_ for _ in ()).throw(AssertionError("should not dispatch")))
    out = _tools()["cassi_dispatch"].func(
        tmp_path, benchmark="L3-003-T1", solver="code/", solution_ref="L3-003-sol-1")
    assert "preview" in out.lower()
    assert GENESIS_SOLUTION_PROVIDER in out
    assert "subgpu" in out


def test_dispatch_confirm_dispatches(tmp_path, monkeypatch):
    (tmp_path / "code").mkdir()
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: _Prov())
    class _Job: job_id = "abc123"
    monkeypatch.setattr(cassi_tools, "dispatch_job", lambda **k: _Job())
    out = _tools()["cassi_dispatch"].func(
        tmp_path, benchmark="L3-003-T1", solver="code/", confirm=True)
    assert "abc123" in out and "cassi_result" in out


def test_dispatch_no_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: None)
    out = _tools()["cassi_dispatch"].func(tmp_path, benchmark="L3-003-T1")
    assert "[cassi error]" in out and "provider" in out.lower()


def test_dispatch_non_mutating():
    assert _tools()["cassi_dispatch"].mutating is False
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Add to `cassi_tools.py`**

Add a module-level import so tests can monkeypatch `cassi_tools.dispatch_job`:

```python
from ai4science.compute.dispatch import dispatch_job
```

Add helpers + the tool (above `cassi_tools()`):

```python
def _resolve_provider(provider_id: str):
    from ai4science.compute.registry import get_provider, load_registry
    if provider_id:
        return get_provider(provider_id)
    regs = load_registry()
    return regs[0] if regs else None


def _solution_cost(solution_ref: str):
    """STUB economics seam → (cost_str, recipient_addr, solution_provider).
    Cost is DEFINED BY THE SOLUTION PROVIDER; users pay PWM to that address. For the
    genesis CASSI solutions the provider is the third founder. The economics layer
    replaces this with a real price lookup + debit + routing."""
    if not solution_ref:
        return ("none (your own solver — compute settled in the economics layer)",
                "you", "you")
    return ("(set by the solution provider — deferred to the economics layer)",
            GENESIS_SOLUTION_PROVIDER, f"of {solution_ref}")


def _dispatch_tool() -> Tool:
    def _dispatch(workspace, *, benchmark: str, solver: str = "code/",
                  provider: str = "", solution_ref: str = "", confirm: bool = False) -> str:
        try:
            prov = _resolve_provider(provider)
            if prov is None:
                return ("[cassi error] no compute provider configured "
                        "(add one with: ai4science compute providers add ...)")
            _contained(Path(workspace), solver)
            cost, recipient, sol_provider = _solution_cost(solution_ref)
            sol_label = solution_ref or "your own solver code"
            if not confirm:
                return ("[preview] would dispatch to sub-GPU compute provider "
                        f"{prov.provider_id} ({prov.endpoint_path})\n"
                        f"  benchmark: {benchmark}\n  solver:    {solver}\n"
                        f"  solution:  {sol_label}\n"
                        f"  PWM cost:  {cost} — pay to {recipient} "
                        f"(solution provider {sol_provider})\n"
                        "Pass confirm=true to dispatch.")
            job = dispatch_job(provider=prov, workspace=Path(workspace).resolve(),
                               benchmark_id=benchmark, solver_code_path=solver)
            return (f"Dispatched job {job.job_id} to sub-GPU provider {prov.provider_id}. "
                    f"PWM cost {cost} → {recipient}. "
                    f"Poll with cassi_result(job_id=\"{job.job_id}\").")
        except CassiError as exc:
            return f"[cassi error] {exc}"
        except Exception as exc:
            return f"[cassi error] {exc}"

    return Tool(
        name="cassi_dispatch",
        description=("Dispatch a reconstruction solver to the sub-GPU compute "
                     "provider for a benchmark. Without confirm=true returns a "
                     "PREVIEW with the PWM cost + recipient (set by the solution "
                     "provider); confirm=true dispatches the job. Running a solution "
                     "costs PWM paid to its provider."),
        parameters={"type": "object", "properties": {
            "benchmark": {"type": "string"}, "solver": {"type": "string"},
            "provider": {"type": "string"}, "solution_ref": {"type": "string"},
            "confirm": {"type": "boolean"}},
            "required": ["benchmark"]},
        func=_dispatch, mutating=False)
```

Update `cassi_tools()`:

```python
def cassi_tools() -> List[Tool]:
    return [_solutions_tool(), _forward_check_tool(), _dispatch_tool()]
```

- [ ] **Step 4: Run → PASS** (5 passed).

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_cassi_dispatch.py -v`

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/cassi_tools.py tests/test_harness_cassi_dispatch.py
git commit -m "feat(cassi): cassi_dispatch (sub-GPU, confirm-guarded, third-founder recipient preview)"
```

---

## Task 4: `cassi_result` (poll + judge → PSNR/score_q)

**Files:**
- Modify: `ai4science/harness/cassi_tools.py`
- Test: `tests/test_harness_cassi_result.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_cassi_result.py
from ai4science.harness import cassi_tools
from ai4science.harness.cassi_tools import cassi_tools as build_cassi_tools


class _Prov:
    provider_id = "subgpu"
    endpoint_path = "/tmp/subgpu_inbox"
    wallet_address = "0xCAFE"


def _tools():
    return {t.name: t for t in build_cassi_tools()}


def test_result_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: _Prov())
    monkeypatch.setattr(cassi_tools, "job_state", lambda ep, jid: {"job_id": jid, "state": "acked"})
    out = _tools()["cassi_result"].func(tmp_path, job_id="abc123")
    assert "acked" in out and "abc123" in out


def test_result_completed_judges(tmp_path, monkeypatch):
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: _Prov())
    monkeypatch.setattr(cassi_tools, "job_state",
                        lambda ep, jid: {"job_id": jid, "state": "completed"})
    monkeypatch.setattr(cassi_tools, "read_result",
                        lambda ep, jid: {"workspace": str(tmp_path), "benchmark_id": "L3-003"})
    monkeypatch.setattr(cassi_tools, "judge_cassi",
                        lambda submission, benchmark=None: {"final": "pass",
                                                            "score_q": 0.93, "psnr_db": 34.0})
    out = _tools()["cassi_result"].func(tmp_path, job_id="abc123")
    assert "0.93" in out and "34.0" in out and "pass" in out


def test_result_no_provider(tmp_path, monkeypatch):
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: None)
    out = _tools()["cassi_result"].func(tmp_path, job_id="abc123")
    assert "[cassi error]" in out


def test_result_completed_no_result_file(tmp_path, monkeypatch):
    monkeypatch.setattr(cassi_tools, "_resolve_provider", lambda pid: _Prov())
    monkeypatch.setattr(cassi_tools, "job_state",
                        lambda ep, jid: {"job_id": jid, "state": "completed"})
    monkeypatch.setattr(cassi_tools, "read_result", lambda ep, jid: None)
    out = _tools()["cassi_result"].func(tmp_path, job_id="abc123")
    assert "[cassi error]" in out
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Add to `cassi_tools.py`**

Add module-level imports (so tests can monkeypatch them on `cassi_tools`):

```python
from ai4science.compute.dispatch import job_state, read_result
from ai4science.judge.cassi.judge_cassi import judge_cassi
```

Add helper + tool (above `cassi_tools()`):

```python
def _judge_summary(report: dict) -> str:
    if not isinstance(report, dict):
        return str(report)
    keys = ("final", "status", "score_q", "psnr_db", "ssim")
    parts = [f"{k}={report[k]}" for k in keys if k in report]
    return ", ".join(parts) or str(report)[:300]


def _result_tool() -> Tool:
    def _result(workspace, *, job_id: str, provider: str = "") -> str:
        try:
            prov = _resolve_provider(provider)
            if prov is None:
                return "[cassi error] no compute provider configured"
            ep = Path(prov.endpoint_path)
            st = job_state(ep, job_id)
            state = st.get("state", "unknown")
            if state != "completed":
                return f"job {job_id}: state={state} (not finished yet)"
            res = read_result(ep, job_id)
            if not res:
                return f"[cassi error] job {job_id} completed but no result file found"
            ws = res.get("workspace") or str(workspace)
            bench = res.get("benchmark_id") or None
            report = judge_cassi(Path(ws), benchmark=bench)
            return f"job {job_id}: completed. judge: {_judge_summary(report)}"
        except Exception as exc:
            return f"[cassi error] {exc}"

    return Tool(
        name="cassi_result",
        description=("Poll a dispatched CASSI job; when completed, judge the result "
                     "and return the physics-judge status + PSNR / score_q."),
        parameters={"type": "object", "properties": {
            "job_id": {"type": "string"}, "provider": {"type": "string"}},
            "required": ["job_id"]},
        func=_result, mutating=False)
```

Update `cassi_tools()`:

```python
def cassi_tools() -> List[Tool]:
    return [_solutions_tool(), _forward_check_tool(), _dispatch_tool(), _result_tool()]
```

- [ ] **Step 4: Run → PASS** (4 passed).

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_cassi_result.py -v`

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/cassi_tools.py tests/test_harness_cassi_result.py
git commit -m "feat(cassi): cassi_result (poll job + judge → PSNR/score_q)"
```

---

## Task 5: Register the bundle + enrich the agent prompt

**Files:**
- Modify: `ai4science/harness/agents/capabilities.py`
- Modify: `ai4science/harness/agents/specs/computational_imaging.py`
- Test: `tests/test_harness_cassi_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_cassi_integration.py
from ai4science.harness.agents import registry, capabilities
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for

_CASSI = {"cassi_solutions", "cassi_forward_check", "cassi_dispatch", "cassi_result"}


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_bundle_registered(tmp_path):
    assert "computational-imaging" in capabilities.CAPABILITY_BUNDLES
    tools = capabilities.resolve_capability("computational-imaging", _ctx(tmp_path))
    assert _CASSI <= {t.name for t in tools}


def test_ci_agent_has_cassi_tools_common_does_not(tmp_path):
    registry.reload()
    spec = registry.get("computational-imaging")
    assert "computational-imaging" in spec.capabilities
    creg = build_registry_for(spec, is_subagent=False, ctx=_ctx(tmp_path))
    assert _CASSI <= set(creg.names())
    common = build_registry_for(registry.get("common"), is_subagent=False, ctx=_ctx(tmp_path))
    assert not (_CASSI & set(common.names()))   # moat: common has none of them
```

- [ ] **Step 2: Run → FAIL** (`computational-imaging` not in bundles).

- [ ] **Step 3a: Register the bundle in `capabilities.py`**

Add a provider after `_pwm_data` (lazy import):

```python
def _computational_imaging(ctx):
    from ai4science.harness.cassi_tools import cassi_tools
    return list(cassi_tools())
```

Add to `CAPABILITY_BUNDLES`:

```python
    "computational-imaging": _computational_imaging,
```

- [ ] **Step 3b: Enrich the prompt + add the bundle in `specs/computational_imaging.py`**

Replace the whole file with:

```python
from ai4science.harness.agents.spec import AgentSpec

PROMPT = (
    "You are AI4Science specialized in COMPUTATIONAL IMAGING — snapshot compressive "
    "spectral imaging (CASSI), reconstruction, and optical encoding.\n\n"
    "Domain: the SD-CASSI forward model y = Φx (coded aperture mask + dispersion "
    "shears the C spectral channels of a cube x:(H,W,C) into a 2-D measurement "
    "y:(H,W+C-1)). Solvers range from classical (GAP-TV, ADMM/TwIST, DeSCI) to deep "
    "unrolled networks (MST, MST-L, DAUHST). Quality is PSNR/SSIM and the registry "
    "score_q; the physics judge runs stages S1 (forward residual), S3, and S4 "
    "(Fourier / noise / spatial consistency).\n\n"
    "Tools: use `cassi_solutions` to survey ALL registered imaging solutions across "
    "mainnet and testnet (note which is which) and ground in the best baselines; "
    "`pwm_solutions`/`pwm_benchmarks` for registry detail; `cassi_forward_check` to "
    "sanity-check a reconstruction's physics locally; then `cassi_dispatch` to run a "
    "solver on the sub-GPU server (it returns a PREVIEW with the PWM cost and the "
    "recipient — running a registered solution costs PWM paid to its solution "
    "provider; confirm=true to actually spend) and `cassi_result` to poll + judge. "
    "Always preview cost before dispatching."
)

AGENT = AgentSpec(
    name="computational-imaging",
    tier="science",
    category="specific",
    title="Computational imaging",
    description="Snapshot/compressive spectral imaging (CASSI): solutions, physics, GPU eval.",
    keywords=("cassi", "spectral", "optics", "reconstruction", "hyperspectral",
              "snapshot", "imaging", "inverse problem"),
    system_prompt=PROMPT,
    capabilities=("pwm-actions", "pwm-data", "computational-imaging"),
)
```

- [ ] **Step 4: Run → PASS** (2 passed). Confirm framework + moat regression:

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_cassi_integration.py tests/test_harness_agents_moat.py tests/test_harness_agents_registry.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/agents/capabilities.py ai4science/harness/agents/specs/computational_imaging.py tests/test_harness_cassi_integration.py
git commit -m "feat(cassi): register computational-imaging bundle + enrich expert prompt"
```

---

## Task 6: Full suite, live E2E, docs

**Files:**
- Modify: `docs/CLAUDE_CODE_PARITY.md`

- [ ] **Step 1: Full suite**

Run: `PYTHONPATH=$(pwd) python3 -m pytest -q`
Expected: green except the 2 pre-existing `test_list_sessions_*` failures. Fix any new red.

- [ ] **Step 2: Live E2E (controller-run; implementer SKIPS network)**

```bash
WS=$(mktemp -d)
printf '/mode specific imaging\n/exit\n' \
| PYTHONPATH=$(pwd) ai4science chat --mode common --workspace "$WS" 2>&1 | tail -6
# Expect: /mode specific imaging lists computational-imaging.

WS2=$(mktemp -d)
printf '/model gemini gemini-3.1-pro-preview\nUse cassi_solutions to list registered imaging solutions and tell me which are mainnet vs testnet. Then preview a cassi_dispatch for benchmark L3-003-001-001-T1 with solution_ref L3-003-sol-1 (do NOT confirm).\n/exit\n' \
| PYTHONPATH=$(pwd) ai4science chat --mode computational-imaging --workspace "$WS2" 2>&1 | tail -25
# Expect: cassi_solutions output marked [testnet] (+ "mainnet: not configured");
# cassi_dispatch PREVIEW showing PWM cost + recipient 0xde81b29...1A29, no spend.
```

- [ ] **Step 3: Docs**

In `docs/CLAUDE_CODE_PARITY.md`, after the "### Paper mode" section, add "### Specific domain agents" (~10 lines): the reusable pattern (a `specs/<domain>.py` AgentSpec + an optional domain capability bundle); computational-imaging as the exemplar with its 4 `cassi_*` tools; the all-solutions-across-chains marking; the cost model (solution-provider-defined PWM, paid to the solution provider — genesis CASSI = third-founder `0xde81…1A29`, charging deferred to economics); GPU on the sub-GPU server via `cassi_dispatch`/`cassi_result`. Match the doc tone.

- [ ] **Step 4: Commit**

```bash
git add docs/CLAUDE_CODE_PARITY.md
git commit -m "docs(cassi): document computational-imaging agent + the domain-agent pattern"
```

---

## After all tasks

1. Final whole-implementation reviewer over `main..feat/ci-agent`.
2. Controller runs the Step 2 live E2E (cassi_solutions marked-by-chain + dispatch preview).
3. `superpowers:finishing-a-development-branch` → merge to `main` locally, then push.
4. Update memory `project_specific_agents.md` → computational-imaging built & merged; record the reusable pattern for biology/chemistry next.
5. Deferred: the PWM-economics spec (real solution-price lookup + debit to the solution provider; compute settled with the sub-GPU provider) — shared with paper-review charging.
