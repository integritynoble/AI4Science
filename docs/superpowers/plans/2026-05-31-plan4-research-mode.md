# Plan 4 — Research Mode (science) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build **research mode** — the same agentic harness as common mode, PLUS read access to the **PWM registry database** (principles / specs / benchmarks) and the **registered solutions** (per-benchmark leaderboards). Common mode does NOT get these tools — that gating is the moat ([[project_research_mode]]). `ai4science chat --mode research` runs the harness with a research tool-set + research system prompt.

**Architecture:** Reuse the native harness (live since Plan 3e). Add a stdlib-`urllib` client for the PWM explorer API (`explorer.physicsworldmodel.org/api`), wrap its endpoints as read-only harness `Tool`s, assemble a `build_research_registry` (common ∪ PWM-data tools), seed a research system prompt, and route `--mode research` to the harness REPL with that registry.

**Tech Stack:** Python 3 stdlib (`urllib`), pytest + monkeypatch, existing `harness/{transport,repl,session,tools}`. No new deps.

**Spec:** verification-grounded design (this session). Data source confirmed live: `https://explorer.physicsworldmodel.org/api/{principles,principles/{id},benchmarks,benchmarks/{ref},leaderboard/{benchmark_id},overview}`. Predecessors: Plans 1/3a/3b/3c/3d/3e merged.

## Confirmed API shapes (grounding)
- `GET /api/principles` → `{"genesis": [{artifact_id, title, domain, sub_domain, difficulty_tier, ...}]}`
- `GET /api/principles/{id}` → `{"principle": {artifact_id, layer, title, domain, source_file, E:{...}, ...}}`
- `GET /api/benchmarks` → `{"genesis": [{artifact_id, parent_l2, parent_l1, title, chain_status, ...}]}`
- `GET /api/leaderboard/{benchmark_id}` → `{benchmark_id, benchmark_title, reference:{label, score_q, psnr_db, metric, tier, source}, reference_advanced:{...}, ...}` — **the registered solutions/baselines + scores.**
- `chain_status` field on artifacts indicates mainnet vs testnet.

## Decisions (v1)
- "Use the solutions" = **read/reference** (fetch leaderboard + artifact detail). Run/reproduce = follow-on (needs compute+judge).
- Single explorer base (`PWM_EXPLORER_BASE`, default `https://explorer.physicsworldmodel.org/api`); tools surface `chain_status`. Mainnet-vs-testnet base switch = future refinement.
- Research system prompt seeded as a `Message(role="system", ...)` — handled by the OpenAI-compat adapter (system role) and the Anthropic adapter (system param).

## File structure

| File | Change |
|---|---|
| `ai4science/harness/transport.py` (modify) | add `get_json(url)` |
| `ai4science/harness/pwm_data.py` (create) | explorer API client |
| `ai4science/harness/research_tools.py` (create) | wrap pwm_data as harness Tools |
| `ai4science/harness/repl.py` (modify) | `build_research_registry`, `RESEARCH_PROMPT`, system-prompt seed, `registry_builder` param |
| `ai4science/commands/chat.py` (modify) | `--mode research` → harness research REPL |
| `tests/test_harness_*.py` | per module |

---

### Task 1: explorer API client + `transport.get_json`

**Files:** Modify `harness/transport.py`; Create `harness/pwm_data.py`; Test `tests/test_harness_pwm_data.py`

- [ ] **Step 1: failing test**
```python
# tests/test_harness_pwm_data.py
from ai4science.harness import pwm_data, transport


def test_principles(monkeypatch):
    monkeypatch.setattr(transport, "get_json",
                        lambda url, timeout=60: {"genesis": [{"artifact_id": "L1-003", "title": "CASSI"}]})
    out = pwm_data.principles()
    assert out[0]["artifact_id"] == "L1-003"


def test_solutions_for_benchmark(monkeypatch):
    monkeypatch.setattr(transport, "get_json",
                        lambda url, timeout=60: {"benchmark_id": "L3-003",
                                                 "reference": {"label": "GAP-TV", "score_q": 0.62},
                                                 "reference_advanced": {"label": "MST-L", "score_q": 0.95}})
    sols = pwm_data.solutions("L3-003")
    labels = {s["label"] for s in sols}
    assert "GAP-TV" in labels and "MST-L" in labels


def test_base_url_env(monkeypatch):
    monkeypatch.setenv("PWM_EXPLORER_BASE", "http://local/api")
    assert pwm_data.base() == "http://local/api"
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** implement.

Add to `harness/transport.py`:
```python
def get_json(url: str, timeout: int = 60) -> Dict[str, Any]:
    req = urllib.request.Request(url, headers={"Accept": "application/json"}, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))
```

`harness/pwm_data.py`:
```python
from __future__ import annotations

import os
from typing import Dict, List

from ai4science.harness import transport

DEFAULT_BASE = "https://explorer.physicsworldmodel.org/api"


def base() -> str:
    return os.environ.get("PWM_EXPLORER_BASE", DEFAULT_BASE).rstrip("/")


def _items(d, *keys) -> List[Dict]:
    if isinstance(d, list):
        return d
    for k in keys:
        v = d.get(k)
        if isinstance(v, list):
            return v
    return []


def principles() -> List[Dict]:
    return _items(transport.get_json(f"{base()}/principles"), "genesis", "principles")


def principle(artifact_id: str) -> Dict:
    d = transport.get_json(f"{base()}/principles/{artifact_id}")
    return d.get("principle", d) if isinstance(d, dict) else d


def benchmarks() -> List[Dict]:
    return _items(transport.get_json(f"{base()}/benchmarks"), "genesis", "benchmarks")


def benchmark(ref: str) -> Dict:
    d = transport.get_json(f"{base()}/benchmarks/{ref}")
    return d.get("benchmark", d) if isinstance(d, dict) else d


def solutions(benchmark_id: str) -> List[Dict]:
    """Registered solutions/baselines + scores for a benchmark (the leaderboard)."""
    d = transport.get_json(f"{base()}/leaderboard/{benchmark_id}")
    out = []
    for key in ("reference", "reference_advanced"):
        s = d.get(key) if isinstance(d, dict) else None
        if isinstance(s, dict):
            out.append({**s, "_kind": key})
    for s in _items(d, "solutions", "submissions", "leaderboard"):
        out.append(s)
    return out


def overview() -> Dict:
    return transport.get_json(f"{base()}/overview")
```

- [ ] **Step 4:** run → PASS (3). `python -m pytest tests/test_harness_*.py -q` no regressions.
- [ ] **Step 5:** commit `feat(harness): PWM explorer API client (principles/benchmarks/solutions) + get_json`.

NOTE: confirm endpoint paths against a live `curl https://explorer.physicsworldmodel.org/api/principles` if network is available; the shapes above are confirmed.

---

### Task 2: research tools (wrap pwm_data as harness Tools)

**Files:** Create `harness/research_tools.py`; Test `tests/test_harness_research_tools.py`

- [ ] **Step 1: failing test**
```python
# tests/test_harness_research_tools.py
from pathlib import Path
from ai4science.harness import research_tools, pwm_data


def test_research_tools_present():
    names = {t.name for t in research_tools.research_tools()}
    assert {"pwm_principles", "pwm_principle", "pwm_benchmarks",
            "pwm_solutions", "pwm_overview"}.issubset(names)
    assert all(t.mutating is False for t in research_tools.research_tools())


def test_pwm_solutions_tool(monkeypatch, tmp_path):
    monkeypatch.setattr(pwm_data, "solutions",
                        lambda bid: [{"label": "MST-L", "score_q": 0.95}])
    tool = {t.name: t for t in research_tools.research_tools()}["pwm_solutions"]
    out = tool.func(tmp_path, benchmark_id="L3-003")
    assert "MST-L" in out and "0.95" in out
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** implement `harness/research_tools.py`:
```python
from __future__ import annotations

import json
from pathlib import Path
from typing import List

from ai4science.harness import pwm_data
from ai4science.harness.tools.base import Tool

_STR = {"type": "string"}


def _wrap(fn, *, takes_arg=None):
    def _tool(workspace: Path, **args) -> str:
        try:
            result = fn(args[takes_arg]) if takes_arg else fn()
        except Exception as exc:
            return f"[pwm error] {exc}"
        return json.dumps(result, indent=2, default=str)[:20000]
    return _tool


def research_tools() -> List[Tool]:
    obj = {"type": "object", "properties": {}}
    id_obj = {"type": "object", "properties": {"artifact_id": _STR}, "required": ["artifact_id"]}
    bench_obj = {"type": "object", "properties": {"benchmark_id": _STR}, "required": ["benchmark_id"]}
    ref_obj = {"type": "object", "properties": {"ref": _STR}, "required": ["ref"]}
    return [
        Tool("pwm_principles", "List PWM registry principles (id/title/domain).", obj,
             _wrap(pwm_data.principles), mutating=False),
        Tool("pwm_principle", "Fetch a PWM principle's full detail by artifact_id.", id_obj,
             _wrap(pwm_data.principle, takes_arg="artifact_id"), mutating=False),
        Tool("pwm_benchmarks", "List PWM benchmarks (id/title/chain_status).", obj,
             _wrap(pwm_data.benchmarks), mutating=False),
        Tool("pwm_benchmark", "Fetch a PWM benchmark by ref.", ref_obj,
             _wrap(pwm_data.benchmark, takes_arg="ref"), mutating=False),
        Tool("pwm_solutions", "Registered SOTA solutions + scores for a benchmark "
             "(the leaderboard). Research mode can build on these.", bench_obj,
             _wrap(pwm_data.solutions, takes_arg="benchmark_id"), mutating=False),
        Tool("pwm_overview", "PWM registry overview.", obj,
             _wrap(pwm_data.overview), mutating=False),
    ]
```

- [ ] **Step 4:** run → PASS (2). no regressions.
- [ ] **Step 5:** commit `feat(harness): research tools (PWM registry + solutions, read-only)`.

---

### Task 3: research registry + system prompt + REPL plumbing

**Files:** Modify `harness/repl.py`; Test `tests/test_harness_research_registry.py`

- [ ] **Step 1: failing test**
```python
# tests/test_harness_research_registry.py
from ai4science.harness.repl import build_research_registry, build_common_registry, RESEARCH_PROMPT


def test_research_registry_has_pwm_data_tools(tmp_path):
    reg = build_research_registry(workspace=tmp_path, session_factory=lambda **k: None)
    names = set(reg.names())
    assert {"read", "edit"}.issubset(names)              # common core
    assert "pwm_solutions" in names and "pwm_principles" in names   # research data tools


def test_common_registry_excludes_research_tools(tmp_path):
    reg = build_common_registry(workspace=tmp_path, session_factory=lambda **k: None)
    names = set(reg.names())
    assert "pwm_solutions" not in names                  # the moat: common can't use solutions


def test_research_prompt_mentions_pwm():
    assert "PWM" in RESEARCH_PROMPT or "principle" in RESEARCH_PROMPT.lower()
```

- [ ] **Step 2:** run → FAIL.
- [ ] **Step 3:** in `harness/repl.py` add:
```python
RESEARCH_PROMPT = (
    "You are AI4Science in RESEARCH mode. In addition to coding tools, you can query "
    "the PWM registry: pwm_principles / pwm_principle, pwm_benchmarks / pwm_benchmark, "
    "pwm_solutions (registered SOTA solutions + scores per benchmark), pwm_overview. "
    "Use registered Principles, Specs, Benchmarks and Solutions to ground your work — "
    "consult pwm_solutions before proposing a new solution, and build on the best "
    "registered baselines. Mainnet/testnet status is shown via each artifact's chain_status."
)


def build_research_registry(*, workspace, session_factory, enable_pwm=True,
                            enable_subagents=True, mcp_clients=None):
    reg = build_common_registry(workspace=workspace, session_factory=session_factory,
                                enable_pwm=enable_pwm, enable_subagents=enable_subagents,
                                mcp_clients=mcp_clients)
    from ai4science.harness.research_tools import research_tools
    for t in research_tools():
        reg.add(t)
    return reg
```
Then make `run_common_repl` accept an optional `registry_builder=None` (defaults to `build_common_registry`) and `system_prompt: Optional[str]=None`. In `_build_session`, use `registry_builder(...)` instead of the hardcoded `build_common_registry(...)`. After `session = _build_session()` (and after any resume seeding), if `system_prompt`, prepend `session.history.insert(0, Message(role="system", content=system_prompt))` (import Message from events). (Place the system message FIRST so adapters see it as the system turn.)

- [ ] **Step 4:** run `python -m pytest tests/test_harness_research_registry.py tests/test_harness_repl.py tests/test_harness_*.py -q` — all green (existing repl tests use the default registry_builder → unchanged).
- [ ] **Step 5:** commit `feat(harness): build_research_registry + research system prompt + registry_builder/system_prompt params`.

---

### Task 4: `--mode research` cutover + full suite + docs + live E2E

**Files:** Modify `harness/repl.py` (research wrapper or chat wiring), `ai4science/commands/chat.py`; Test `tests/test_chat.py` (research routes to harness)

- [ ] **Step 1: failing test** — add to `tests/test_chat.py`:
```python
def test_chat_research_uses_harness(tmp_path, monkeypatch):
    """--mode research now routes to the native harness research REPL (not the SDK path)."""
    monkeypatch.chdir(tmp_path)
    called = {}
    monkeypatch.setattr("ai4science.harness.repl.run_common_repl",
                        lambda workspace, **kw: called.update(kw))
    result = runner.invoke(app, ["chat", "--mode", "research"])
    assert result.exit_code == 0
    assert called.get("registry_builder") is not None     # research registry passed
    assert called.get("system_prompt")                    # research prompt passed
```

- [ ] **Step 2:** run → FAIL (research still routes to `_run_chat`/SDK).
- [ ] **Step 3:** in `chat.py`, change the mode handling so `mode == "research"` ALSO routes to the harness `run_common_repl`, passing `registry_builder=build_research_registry` and `system_prompt=RESEARCH_PROMPT`. Concretely, generalize the existing `if mode == "common":` branch to handle both:
```python
    if mode in ("common", "research"):
        from ai4science.harness.repl import (run_common_repl, build_common_registry,
                                             build_research_registry, RESEARCH_PROMPT)
        from ai4science.harness import persistence
        resume_hist = None; sid = resume
        if resume:
            resume_hist = persistence.load(resume)
        elif continue_session:
            sid = persistence.most_recent(workspace)
            resume_hist = persistence.load(sid) if sid else None
        rb = build_research_registry if mode == "research" else build_common_registry
        sp = RESEARCH_PROMPT if mode == "research" else None
        try:
            run_common_repl(workspace, read_only=read_only or plan, auto_yes=yes, model=model,
                            resume_history=resume_hist, session_id=sid,
                            registry_builder=rb, system_prompt=sp)
        except KeyboardInterrupt:
            console.print("\n[dim](Ctrl-C — exiting)[/dim]"); raise typer.Exit(0)
        return
```
(The old `_run_chat` SDK research path is now superseded; leave `_run_chat` in place for `--agent` legacy but it's no longer reached for research. Keep research-mode banner text if desired.)

- [ ] **Step 4:** `python -m pytest -q` (green except the 2 pre-existing env failures). Update `docs/CLAUDE_CODE_PARITY.md` / a research-mode note: research mode = harness + PWM registry/solutions (read), common mode excluded; data via explorer API.
- [ ] **Step 5: LIVE E2E (network):**
  ```
  printf 'use pwm_solutions to list the registered solutions for benchmark L3-003 and summarize the best one\n/exit\n' | ai4science chat --mode research --workspace <repo>
  ```
  Expect: the agent calls `pwm_solutions("L3-003")`, gets GAP-TV/MST-L scores from the live explorer, and summarizes MST-L (score_q 0.95). Capture the pane.
- [ ] **Step 6:** commit `feat(harness): --mode research → harness with PWM registry/solutions; docs + live E2E`.

---

## Self-review
- **Coverage:** explorer client (T1), research tools (T2), research registry + prompt + plumbing (T3), `--mode research` cutover + live E2E (T4). The moat is enforced: `build_common_registry` has NO pwm-data tools; `build_research_registry` adds them — tested directly.
- **Placeholder scan:** every step has concrete code; API shapes confirmed live.
- **Type consistency:** `Tool(name, description, parameters, func, mutating)`; `run_common_repl(..., registry_builder=, system_prompt=)`; system seeded as `Message(role="system")` (OpenAI-compat + Anthropic both handle it; the Gemini-native adapter is unused).

## Known limitations
1. v1 reads solutions (fetch/reference); running/reproducing a registered solution (compute+judge) is a follow-on.
2. Single explorer base; mainnet-vs-testnet is surfaced via `chain_status`, not a base switch.
3. The explorer currently indexes the testnet chain (per `chain_status`); when mainnet indexing is primary, no code change is needed (same endpoints).
