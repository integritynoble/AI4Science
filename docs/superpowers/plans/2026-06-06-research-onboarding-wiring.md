# Research-Mode Onboarding Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the research (science-tier) agent the PWM easy-onboarding UX layer — an `onboarding` capability bundle with 4 tools (`onboard_guide`/`onboard_submit`/`onboard_status`/`onboard_balance`) that author + submit an artifact to the live `pwm_nonprofit` API and read the PWM reward.

**Architecture:** A new `ai4science/harness/onboard_tools.py` holds the 4 tools + self-contained urllib HTTP helpers (Bearer auth with the user's `pwm_…` API key). The `onboarding` capability bundle (in `capabilities.py`) returns `onboard_tools()`; the `research` AgentSpec lists it (science-tier → moat keeps it out of common). `onboard_submit` writes to the LIVE platform and is strict-boolean confirm-guarded (preview unless `confirm is True`). On-chain promotion (M6) is out of scope.

**Tech Stack:** Python 3, stdlib only (`urllib`, `json`, `os`, `re`), pytest. No new deps.

**Spec:** `docs/superpowers/specs/2026-06-06-research-onboarding-wiring-design.md` (read it).

**Live API (verified from `pwm_nonprofit`):**
- `POST /api/v1/pwm-submit/{slug}` (Form): principle→`name,domain,rule,formula,reference`; **spec** (digital-twin)→`principle_id,operator_type,omega_description,epsilon,reference`; benchmark→`spec_id,tier,dataset_description,metric,metric_threshold[,dataset_url]`; solution→`principle_id,ai_system,task_description,artifact_description[,self_reported_metric]`. Returns HTML.
- `GET /api/v1/pwm-token/balance` → `{"success":true,...}`; `GET /api/v1/pwm-token/transactions?limit=` → `{"success":true,"transactions":[...]}`. (JSON.)
- Auth: `Authorization: Bearer pwm_…` (personal API key). Config env: `PWM_ONBOARD_BASE` (default `https://physicsworldmodel.org`), `PWM_ONBOARD_TOKEN`.

**Run tests:** `PYTHONPATH=$(pwd) python3 -m pytest <path> -v` from the repo root (`python3`). Baseline on `main`: `449 passed, 4 skipped, 2 failed` (the 2 = pre-existing `test_chat.py::test_list_sessions_*`, `claude_agent_sdk` absent; leave them).

**Branch:** create `feat/research-onboarding` off `main` before Task 1.

**SAFETY:** never run a real production `onboard_submit(confirm=True)` against the live platform during implementation/verification — it creates a real submission + reward. Tests use mocked HTTP; the live E2E exercises only `onboard_guide`, the `onboard_submit` **preview**, and the no-token message.

---

## File Structure

| File | Responsibility |
|---|---|
| `ai4science/harness/onboard_tools.py` | field schema + `_base`/`_token`/`_post_form`/`_get_json` + 4 tools + `onboard_tools()` |
| `ai4science/harness/agents/capabilities.py` | (modify) register the `onboarding` bundle |
| `ai4science/harness/agents/specs/research.py` | (modify) add `onboarding` capability + prompt steer |
| `docs/CLAUDE_CODE_PARITY.md` | (modify) document the onboarding wiring |
| `tests/test_harness_onboard_*.py` | unit tests per tool |

`onboard_tools()` grows one tool per task; the integration test (Task 4) asserts all 4.

---

## Task 1: Scaffold `onboard_tools.py` + `onboard_guide`

**Files:**
- Create: `ai4science/harness/onboard_tools.py`
- Test: `tests/test_harness_onboard_guide.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_onboard_guide.py
from ai4science.harness.onboard_tools import onboard_tools as build


def _tools():
    return {t.name: t for t in build()}


def test_guide_principle(tmp_path):
    out = _tools()["onboard_guide"].func(tmp_path, artifact_type="principle")
    for f in ("name", "domain", "rule", "formula", "reference"):
        assert f in out
    assert "pwm-submit/principle" in out


def test_guide_digital_twin_maps_to_spec(tmp_path):
    out = _tools()["onboard_guide"].func(tmp_path, artifact_type="digital-twin")
    assert "pwm-submit/spec" in out and "operator_type" in out


def test_guide_unknown_type(tmp_path):
    out = _tools()["onboard_guide"].func(tmp_path, artifact_type="nope")
    assert "[onboard error]" in out


def test_guide_tool_non_mutating():
    assert _tools()["onboard_guide"].mutating is False
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError: ... onboard_tools`).

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_onboard_guide.py -v`

- [ ] **Step 3: Create `ai4science/harness/onboard_tools.py`**

```python
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import List

from ai4science.harness.tools.base import Tool

# artifact_type -> (endpoint_slug, required_fields, optional_fields)
_TYPES = {
    "principle": ("principle",
                  ("name", "domain", "rule", "formula", "reference"), ()),
    "digital-twin": ("spec",
                     ("principle_id", "operator_type", "omega_description",
                      "epsilon", "reference"), ()),
    "benchmark": ("benchmark",
                  ("spec_id", "tier", "dataset_description", "metric",
                   "metric_threshold"), ("dataset_url",)),
    "solution": ("solution",
                 ("principle_id", "ai_system", "task_description",
                  "artifact_description"), ("self_reported_metric",)),
}
_HOWTO = {
    "principle": "A physical law: a named rule + formula + a citation, in a domain.",
    "digital-twin": "An L2 spec under a principle: the operator/Omega/epsilon of a simulation.",
    "benchmark": "An L3 benchmark under a spec: dataset + metric + threshold (+ tier).",
    "solution": "An L4 solution under a principle: the AI system, task, and artifact.",
}


def _base() -> str:
    return os.environ.get("PWM_ONBOARD_BASE", "https://physicsworldmodel.org").rstrip("/")


def _token():
    return os.environ.get("PWM_ONBOARD_TOKEN")


def _guide_tool() -> Tool:
    def _guide(workspace, *, artifact_type: str) -> str:
        t = _TYPES.get(artifact_type)
        if not t:
            return (f"[onboard error] unknown type {artifact_type!r}; one of: "
                    f"{', '.join(_TYPES)}")
        slug, req, opt = t
        lines = [f"{artifact_type} (POST /api/v1/pwm-submit/{slug})",
                 "required: " + ", ".join(req)]
        if opt:
            lines.append("optional: " + ", ".join(opt))
        lines.append(_HOWTO[artifact_type])
        return "\n".join(lines)

    return Tool(
        name="onboard_guide",
        description=("Show the required/optional fields + how-to for authoring a PWM "
                     "artifact to submit: artifact_type one of principle / "
                     "digital-twin / benchmark / solution."),
        parameters={"type": "object", "properties": {
            "artifact_type": {"type": "string"}}, "required": ["artifact_type"]},
        func=_guide, mutating=False)


def onboard_tools() -> List[Tool]:
    return [_guide_tool()]
```

- [ ] **Step 4: Run → PASS** (4 passed).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/onboard_tools.py tests/test_harness_onboard_guide.py
git commit -m "feat(onboard): onboard_guide + field schema scaffold"
```

---

## Task 2: `onboard_balance` + `onboard_status` (JSON reads)

**Files:**
- Modify: `ai4science/harness/onboard_tools.py`
- Test: `tests/test_harness_onboard_read.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_onboard_read.py
from ai4science.harness import onboard_tools
from ai4science.harness.onboard_tools import onboard_tools as build


def _tools():
    return {t.name: t for t in build()}


def test_balance_no_token(tmp_path, monkeypatch):
    monkeypatch.delenv("PWM_ONBOARD_TOKEN", raising=False)
    out = _tools()["onboard_balance"].func(tmp_path)
    assert "[onboard error]" in out and "PWM_ONBOARD_TOKEN" in out


def test_balance_ok(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_ONBOARD_TOKEN", "pwm_abc")
    monkeypatch.setattr(onboard_tools, "_get_json",
                        lambda path: {"success": True, "balance": 0.3, "daily_remaining": 1.7})
    out = _tools()["onboard_balance"].func(tmp_path)
    assert "0.3" in out and "success" not in out


def test_status_lists_transactions(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_ONBOARD_TOKEN", "pwm_abc")
    monkeypatch.setattr(onboard_tools, "_get_json",
                        lambda path: {"success": True, "transactions": [
                            {"kind": "award", "amount": 0.1, "status": "accepted",
                             "created_at": "2026-06-06"}]})
    out = _tools()["onboard_status"].func(tmp_path)
    assert "award" in out and "0.1" in out and "accepted" in out


def test_status_no_token(tmp_path, monkeypatch):
    monkeypatch.delenv("PWM_ONBOARD_TOKEN", raising=False)
    out = _tools()["onboard_status"].func(tmp_path)
    assert "[onboard error]" in out
```

- [ ] **Step 2: Run → FAIL** (`KeyError: 'onboard_balance'`).

- [ ] **Step 3: Add to `onboard_tools.py`**

Add the `_get_json` helper (module level, above `onboard_tools()`):

```python
def _get_json(path: str) -> dict:
    req = urllib.request.Request(_base() + path, method="GET", headers={
        "Authorization": f"Bearer {_token()}", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8"))


def _balance_tool() -> Tool:
    def _balance(workspace) -> str:
        if not _token():
            return ("[onboard error] set PWM_ONBOARD_TOKEN (your pwm_ API key from "
                    "physicsworldmodel.org)")
        try:
            d = _get_json("/api/v1/pwm-token/balance")
        except Exception as exc:
            return f"[onboard error] {exc}"
        return json.dumps({k: v for k, v in d.items() if k != "success"},
                          indent=2, default=str)[:20000]

    return Tool(
        name="onboard_balance",
        description="Show the contributor's PWM token balance + caps (needs PWM_ONBOARD_TOKEN).",
        parameters={"type": "object", "properties": {}, "required": []},
        func=_balance, mutating=False)


def _status_tool() -> Tool:
    def _status(workspace) -> str:
        if not _token():
            return ("[onboard error] set PWM_ONBOARD_TOKEN (your pwm_ API key from "
                    "physicsworldmodel.org)")
        try:
            d = _get_json("/api/v1/pwm-token/transactions?limit=20")
        except Exception as exc:
            return f"[onboard error] {exc}"
        txns = d.get("transactions") or []
        if not txns:
            return "no PWM transactions yet."
        lines = []
        for t in txns[:20]:
            lines.append(f"- {t.get('kind') or t.get('type') or '?'} "
                         f"{t.get('amount')} ({t.get('status') or ''}) "
                         f"{t.get('created_at') or t.get('timestamp') or ''}")
        return "\n".join(lines)[:20000]

    return Tool(
        name="onboard_status",
        description=("Show recent PWM ledger entries (the accept-reward trail for your "
                     "submissions; needs PWM_ONBOARD_TOKEN)."),
        parameters={"type": "object", "properties": {}, "required": []},
        func=_status, mutating=False)
```

Update `onboard_tools()`:

```python
def onboard_tools() -> List[Tool]:
    return [_guide_tool(), _status_tool(), _balance_tool()]
```

- [ ] **Step 4: Run → PASS** (4 passed). Re-run Task 1 test for no regression.

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_onboard_read.py tests/test_harness_onboard_guide.py -v`

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/onboard_tools.py tests/test_harness_onboard_read.py
git commit -m "feat(onboard): onboard_balance + onboard_status (JSON ledger reads, Bearer)"
```

---

## Task 3: `onboard_submit` (validate + strict confirm-guard + POST)

**Files:**
- Modify: `ai4science/harness/onboard_tools.py`
- Test: `tests/test_harness_onboard_submit.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_onboard_submit.py
from ai4science.harness import onboard_tools
from ai4science.harness.onboard_tools import onboard_tools as build


def _tools():
    return {t.name: t for t in build()}


_GOOD = {"name": "Energy Conservation", "domain": "mechanics",
         "rule": "energy is conserved", "formula": "dE/dt=0", "reference": "Noether 1918"}


def test_submit_missing_fields(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_ONBOARD_TOKEN", "pwm_abc")
    out = _tools()["onboard_submit"].func(
        tmp_path, artifact_type="principle", fields={"name": "x"})
    assert "[onboard error]" in out and "missing" in out.lower()


def test_submit_no_token(tmp_path, monkeypatch):
    monkeypatch.delenv("PWM_ONBOARD_TOKEN", raising=False)
    out = _tools()["onboard_submit"].func(
        tmp_path, artifact_type="principle", fields=_GOOD)
    assert "[onboard error]" in out and "PWM_ONBOARD_TOKEN" in out


def test_submit_preview_no_post(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_ONBOARD_TOKEN", "pwm_abc")
    monkeypatch.setattr(onboard_tools, "_post_form",
                        lambda path, fields: (_ for _ in ()).throw(AssertionError("must not POST")))
    out = _tools()["onboard_submit"].func(
        tmp_path, artifact_type="principle", fields=_GOOD)   # confirm omitted
    assert "preview" in out.lower() and "pwm-submit/principle" in out


def test_submit_string_confirm_does_not_post(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_ONBOARD_TOKEN", "pwm_abc")
    monkeypatch.setattr(onboard_tools, "_post_form",
                        lambda path, fields: (_ for _ in ()).throw(AssertionError("must not POST")))
    out = _tools()["onboard_submit"].func(
        tmp_path, artifact_type="principle", fields=_GOOD, confirm="true")
    assert "preview" in out.lower()


def test_submit_confirm_posts(tmp_path, monkeypatch):
    monkeypatch.setenv("PWM_ONBOARD_TOKEN", "pwm_abc")
    seen = {}
    def fake_post(path, fields):
        seen["path"] = path; seen["fields"] = fields
        return 200, "<div>Submission <b>accepted</b></div>"
    monkeypatch.setattr(onboard_tools, "_post_form", fake_post)
    out = _tools()["onboard_submit"].func(
        tmp_path, artifact_type="digital-twin",
        fields={"principle_id": "P1", "operator_type": "ODE",
                "omega_description": "domain", "epsilon": "0.01", "reference": "ref"},
        confirm=True)
    assert seen["path"] == "/api/v1/pwm-submit/spec"
    assert seen["fields"]["operator_type"] == "ODE"
    assert "submitted" in out.lower() and "accepted" in out.lower()


def test_submit_non_mutating():
    assert _tools()["onboard_submit"].mutating is False
```

- [ ] **Step 2: Run → FAIL.**

- [ ] **Step 3: Add to `onboard_tools.py`**

Add `_post_form` + `_extract_badge` + the tool (above `onboard_tools()`):

```python
def _post_form(path: str, fields: dict):
    data = urllib.parse.urlencode({k: str(v) for k, v in fields.items()}).encode()
    req = urllib.request.Request(_base() + path, data=data, method="POST", headers={
        "Authorization": f"Bearer {_token()}",
        "Content-Type": "application/x-www-form-urlencoded"})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def _extract_badge(html: str):
    m = re.search(r"(accepted|rejected|pending|verifying|under review)", html or "", re.I)
    return m.group(1).lower() if m else None


def _submit_tool() -> Tool:
    def _submit(workspace, *, artifact_type: str, fields, confirm: bool = False) -> str:
        confirm = confirm is True   # strict: a string "true"/"false" never submits
        t = _TYPES.get(artifact_type)
        if not t:
            return (f"[onboard error] unknown type {artifact_type!r}; one of: "
                    f"{', '.join(_TYPES)}")
        slug, req, opt = t
        if not isinstance(fields, dict):
            return "[onboard error] fields must be an object of field->value"
        missing = [f for f in req if not str(fields.get(f, "")).strip()]
        if missing:
            return f"[onboard error] missing fields: {', '.join(missing)}"
        if not _token():
            return ("[onboard error] set PWM_ONBOARD_TOKEN (your pwm_ API key from "
                    "physicsworldmodel.org)")
        allowed = set(req) | set(opt)
        payload = {k: v for k, v in fields.items() if k in allowed}
        if not confirm:
            body = "\n".join(f"  {k}: {v}" for k, v in payload.items())
            return (f"[preview] would submit a {artifact_type} to "
                    f"{_base()}/api/v1/pwm-submit/{slug}\n{body}\n"
                    "Pass confirm=true to submit to the LIVE platform "
                    "(it runs the S1-S4 quality gate and may award PWM).")
        try:
            status, text = _post_form(f"/api/v1/pwm-submit/{slug}", payload)
        except Exception as exc:
            return f"[onboard error] {exc}"
        if status >= 400:
            return f"[onboard error] submit failed (HTTP {status})"
        badge = _extract_badge(text)
        return (f"Submitted {artifact_type} (HTTP {status}"
                f"{', status: ' + badge if badge else ''}). "
                "Check onboard_status / onboard_balance for the gate result + reward.")

    return Tool(
        name="onboard_submit",
        description=("Submit an authored PWM artifact to the live platform. Args: "
                     "artifact_type (principle/digital-twin/benchmark/solution), "
                     "fields (an object of the required fields from onboard_guide), "
                     "confirm. Without confirm=true it PREVIEWS (no write); confirm=true "
                     "submits to the live platform (runs the S1-S4 gate, may award PWM)."),
        parameters={"type": "object", "properties": {
            "artifact_type": {"type": "string"},
            "fields": {"type": "object"},
            "confirm": {"type": "boolean"}},
            "required": ["artifact_type", "fields"]},
        func=_submit, mutating=False)
```

Update `onboard_tools()`:

```python
def onboard_tools() -> List[Tool]:
    return [_guide_tool(), _submit_tool(), _status_tool(), _balance_tool()]
```

- [ ] **Step 4: Run → PASS** (6 passed).

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_onboard_submit.py -v`

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/onboard_tools.py tests/test_harness_onboard_submit.py
git commit -m "feat(onboard): onboard_submit (validate + strict confirm-guard + Bearer POST)"
```

---

## Task 4: Register the bundle + wire research

**Files:**
- Modify: `ai4science/harness/agents/capabilities.py`
- Modify: `ai4science/harness/agents/specs/research.py`
- Test: `tests/test_harness_onboard_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_onboard_integration.py
from ai4science.harness.agents import registry, capabilities
from ai4science.harness.agents.context import BuildContext
from ai4science.harness.agents.registry import build_registry_for

_ONB = {"onboard_guide", "onboard_submit", "onboard_status", "onboard_balance"}


def _ctx(tmp_path):
    return BuildContext(workspace=tmp_path, brand_provider=lambda: ("gemini", "m"),
                        session_factory=lambda **k: None)


def test_bundle_registered(tmp_path):
    assert "onboarding" in capabilities.CAPABILITY_BUNDLES
    tools = capabilities.resolve_capability("onboarding", _ctx(tmp_path))
    assert _ONB <= {t.name for t in tools}


def test_research_has_onboarding_common_does_not(tmp_path):
    registry.reload()
    research = registry.get("research")
    assert "onboarding" in research.capabilities
    rreg = build_registry_for(research, is_subagent=False, ctx=_ctx(tmp_path))
    assert _ONB <= set(rreg.names())
    common = build_registry_for(registry.get("common"), is_subagent=False, ctx=_ctx(tmp_path))
    assert not (_ONB & set(common.names()))   # moat
```

- [ ] **Step 2: Run → FAIL** (`onboarding` not in CAPABILITY_BUNDLES).

- [ ] **Step 3a: Register the bundle in `capabilities.py`**

Add a provider after `_pwm_data` (lazy import):

```python
def _onboarding(ctx):
    from ai4science.harness.onboard_tools import onboard_tools
    return list(onboard_tools())
```

Add to `CAPABILITY_BUNDLES`:

```python
    "onboarding": _onboarding,
```

- [ ] **Step 3b: Wire `research` in `specs/research.py`**

Change `capabilities=("pwm-actions", "pwm-data")` to:

```python
    capabilities=("pwm-actions", "pwm-data", "onboarding"),
```

And append this onboarding steer to the END of the `RESEARCH_PROMPT` string (before the closing `)`):

```
" You can also help a contributor put an artifact on PWM and earn PWM: use "
"onboard_guide for the required fields of a principle/digital-twin/benchmark/"
"solution, ground it with the pwm_* tools, then onboard_submit (it PREVIEWS "
"first - pass confirm=true to submit to the live platform, which runs the S1-S4 "
"quality gate and awards PWM on accept). Track the reward with onboard_status / "
"onboard_balance. Always preview before submitting."
```

(Keep the existing prompt text; just concatenate this sentence onto it.)

- [ ] **Step 4: Run → PASS** (2 passed). Confirm framework + moat regression:

Run: `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_onboard_integration.py tests/test_harness_agents_moat.py tests/test_harness_agents_registry.py tests/test_harness_research_registry.py -v`
Expected: all pass. (If `test_harness_research_registry.py` asserts research's exact tool set, update it to also accept the `onboard_*` tools — keep it meaningful: research has `pwm_solutions` AND `onboard_submit`; common has neither.)

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/agents/capabilities.py ai4science/harness/agents/specs/research.py tests/test_harness_onboard_integration.py
git commit -m "feat(onboard): register onboarding bundle + wire research (science-tier moat)"
```

---

## Task 5: Full suite, live E2E (safe), docs

**Files:**
- Modify: `docs/CLAUDE_CODE_PARITY.md`

- [ ] **Step 1: Full suite**

Run: `PYTHONPATH=$(pwd) python3 -m pytest -q`
Expected: green except the 2 pre-existing `test_list_sessions_*` failures.

- [ ] **Step 2: Live E2E (controller-run; SAFE paths only — NO real submit)**

```bash
# /mode research has the onboarding tools; guide + preview + no-token message work.
WS=$(mktemp -d)
printf '/model gemini gemini-3.1-pro-preview\nUse onboard_guide to show the fields for a principle. Then PREVIEW an onboard_submit of a principle named "Test Law" (domain mechanics, rule "x", formula "y", reference "z") WITHOUT confirming. Then call onboard_balance.\n/exit\n' \
| PYTHONPATH=$(pwd) ai4science chat --mode research --workspace "$WS" 2>&1 | tail -25
# Expect: guide lists name/domain/rule/formula/reference; onboard_submit returns a
# [preview] (no write); onboard_balance returns "[onboard error] set PWM_ONBOARD_TOKEN"
# (no token configured here). DO NOT pass confirm=true.
```

- [ ] **Step 3: Docs**

In `docs/CLAUDE_CODE_PARITY.md`, after the "### Specific domain agents" section, add "### Research onboarding (PWM contribution)" (~10 lines): research (science-tier) is the easy-onboarding UX layer — the `onboarding` bundle's 4 tools (`onboard_guide`/`onboard_submit`/`onboard_status`/`onboard_balance`) author + submit an artifact to the live `pwm_nonprofit` API (Bearer `pwm_…` key via `PWM_ONBOARD_TOKEN`, base `PWM_ONBOARD_BASE`) and read the PWM reward; `onboard_submit` is confirm-guarded (preview unless `confirm=true`); science-tier moat keeps it out of common; on-chain promotion (M6 relay) is out of scope. Match the doc tone.

- [ ] **Step 4: Commit**

```bash
git add docs/CLAUDE_CODE_PARITY.md
git commit -m "docs(onboard): document research onboarding wiring"
```

---

## After all tasks

1. Final whole-implementation reviewer over `main..feat/research-onboarding` (focus: the confirm-guard can't write without `confirm is True`; the moat; no token leakage in errors).
2. Controller runs the Step-2 live E2E (guide + preview + no-token), NO real submit.
3. `superpowers:finishing-a-development-branch` → merge to `main` locally, then push.
4. Update memory `project_research_onboarding.md` → built & merged.
5. Follow-ups: a JSON `GET /api/v1/pwm-submit/status/{id}` on the `pwm_nonprofit` backend (crisp per-submission status); on-chain promotion (M6 relay/payer); add `onboarding` to other science agents if wanted.
