# PWM Usage Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax. NOTE: the controller will verify every file against disk after each task.

**Goal:** Enforce "no free tier" — the AI4Science agent requires earned PWM: block a turn when the user's PWM balance is ≤ 0, and debit the metered per-turn PWM to the provider wallet after each turn (off-chain ledger; no mainnet). PWM is earned by contributing; this only *spends* it among providers — never a platform sale/charge.

**Architecture:** A new `ai4science/harness/pwm_gate.py` (`PwmGate`) talks to the live `pwm_nonprofit` PWM-ledger API with the user's `pwm_…` key: `GET /api/v1/pwm-token/balance` to check, `POST /api/v1/pwm-token/spend` (402-aware, idempotent) to debit→credit the provider. The REPL builds the gate from env, checks before each turn, and charges the metered PWM after. The agent already computes per-call PWM + provider wallet in `make_meter` (`routing._select_source` + `pricing.price_call`); the wrapped meter accumulates the turn's PWM + wallet for the charge. **Disabled by default** (enable via `AI4SCIENCE_PWM_GATE` + a token) so dev/CI/tests run free.

**Tech Stack:** Python 3, stdlib (`urllib`, `json`, `os`), pytest. No new deps.

**Backend contract (verified from `pwm_nonprofit/routers/pwm_token.py`):**
- `GET /api/v1/pwm-token/balance` → `{"success":true,"balance":<float>,"lifetime_earned":...}` (Bearer `pwm_…`).
- `POST /api/v1/pwm-token/spend` body `{amount, purpose, provider_wallet, idempotency_key}` → `{success, transaction_id, balance_after, ...}`; **HTTP 402** if insufficient; **idempotent** on `idempotency_key`.

**Run tests:** `PYTHONPATH=$(pwd) python3 -m pytest <path> -v` from the repo root (`python3`). Baseline on `main`: `466 passed, 4 skipped, 2 failed` (the 2 = pre-existing `test_list_sessions_*`, claude_agent_sdk absent).

**Branch:** create `feat/pwm-usage-gate` off `main`.

---

## Task 1: `pwm_gate.py` — the gate (check + charge)

**Files:**
- Create: `ai4science/harness/pwm_gate.py`
- Test: `tests/test_harness_pwm_gate.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_harness_pwm_gate.py
from ai4science.harness import pwm_gate
from ai4science.harness.pwm_gate import PwmGate


def _gate(enabled=True, **kw):
    return PwmGate(token="pwm_k", base="https://x", enabled=enabled, **kw)


def test_disabled_gate_always_allows(monkeypatch):
    g = PwmGate(token=None, base="https://x", enabled=False)
    assert g.check()[0] is True
    assert g.charge(1.0, "0xWALLET", "p", "idem")[0] is True   # no-op


def test_check_allows_with_positive_balance(monkeypatch):
    g = _gate()
    monkeypatch.setattr(g, "_get_balance", lambda: 0.5)
    allowed, reason = g.check()
    assert allowed is True and reason == ""


def test_check_blocks_on_zero_balance(monkeypatch):
    g = _gate()
    monkeypatch.setattr(g, "_get_balance", lambda: 0.0)
    allowed, reason = g.check()
    assert allowed is False and "earn pwm" in reason.lower() and "[pwm]" in reason.lower()


def test_check_blocks_when_balance_unavailable(monkeypatch):
    g = _gate()
    monkeypatch.setattr(g, "_get_balance", lambda: None)
    allowed, reason = g.check()
    assert allowed is False and "[pwm]" in reason.lower()


def test_charge_posts_spend(monkeypatch):
    g = _gate()
    seen = {}
    def fake_post(path, body):
        seen["path"] = path; seen["body"] = body
        return 200, {"success": True, "balance_after": 0.4}
    monkeypatch.setattr(g, "_post", fake_post)
    ok, reason = g.charge(0.1, "0xWALLET", "ai4science:common:gpt", "sid:1")
    assert ok is True
    assert seen["path"] == "/api/v1/pwm-token/spend"
    assert seen["body"]["amount"] == 0.1 and seen["body"]["provider_wallet"] == "0xWALLET"
    assert seen["body"]["idempotency_key"] == "sid:1"


def test_charge_402_reports_exhausted(monkeypatch):
    g = _gate()
    monkeypatch.setattr(g, "_post", lambda path, body: (402, {"detail": "insufficient"}))
    ok, reason = g.charge(0.1, "0xW", "p", "idem")
    assert ok is False and "[pwm]" in reason.lower()


def test_charge_zero_amount_is_noop(monkeypatch):
    g = _gate()
    monkeypatch.setattr(g, "_post", lambda p, b: (_ for _ in ()).throw(AssertionError("no post")))
    assert g.charge(0.0, "0xW", "p", "idem")[0] is True


def test_from_env_enabled_requires_flag_and_token(monkeypatch):
    monkeypatch.delenv("AI4SCIENCE_PWM_GATE", raising=False)
    monkeypatch.setenv("PWM_TOKEN", "pwm_k")
    assert PwmGate.from_env().enabled is False           # flag off → disabled
    monkeypatch.setenv("AI4SCIENCE_PWM_GATE", "1")
    assert PwmGate.from_env().enabled is True
    monkeypatch.delenv("PWM_TOKEN", raising=False)
    monkeypatch.delenv("PWM_ONBOARD_TOKEN", raising=False)
    assert PwmGate.from_env().enabled is False           # no token → disabled
```

- [ ] **Step 2: Run → FAIL** (`ModuleNotFoundError`).

- [ ] **Step 3: Create `ai4science/harness/pwm_gate.py`**

```python
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional, Tuple

_EARN = ("Earn PWM by submitting verified principles, specs, benchmarks, or solutions "
         "(physicsworldmodel.org) — every AI4Science turn costs PWM.")


def _truthy(v) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


class PwmGate:
    """Gate the agent on the user's earned PWM balance (off-chain ledger).

    check() blocks a turn when balance <= min_balance; charge() debits the metered
    per-turn PWM to the provider wallet via /spend. Disabled unless AI4SCIENCE_PWM_GATE
    is set AND a pwm_ token is present (so dev/CI run free)."""

    def __init__(self, *, token: Optional[str], base: str, enabled: bool,
                 min_balance: float = 0.0):
        self.token = token
        self.base = (base or "").rstrip("/")
        self.enabled = enabled
        self.min_balance = min_balance

    # ── HTTP (Bearer) ──
    def _get(self, path: str) -> dict:
        req = urllib.request.Request(self.base + path, method="GET", headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    def _post(self, path: str, body: dict):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method="POST", headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
            "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode("utf-8"))
            except Exception:
                return e.code, {}

    def _get_balance(self) -> Optional[float]:
        try:
            d = self._get("/api/v1/pwm-token/balance")
            b = d.get("balance")
            return float(b) if b is not None else None
        except Exception:
            return None

    # ── gate API ──
    def check(self) -> Tuple[bool, str]:
        if not self.enabled:
            return True, ""
        bal = self._get_balance()
        if bal is None:
            return False, ("[pwm] could not verify your PWM balance (set PWM_TOKEN to your "
                           "pwm_ key). " + _EARN)
        if bal <= self.min_balance:
            return False, (f"[pwm] insufficient PWM (balance {bal:.3f}). " + _EARN)
        return True, ""

    def charge(self, amount: float, provider_wallet: Optional[str], purpose: str,
               idempotency_key: str) -> Tuple[bool, str]:
        if not self.enabled or not amount or amount <= 0:
            return True, ""
        status, data = self._post("/api/v1/pwm-token/spend", {
            "amount": round(float(amount), 6),
            "purpose": purpose,
            "provider_wallet": provider_wallet,
            "idempotency_key": idempotency_key,
        })
        if status == 402:
            return False, "[pwm] balance exhausted mid-session. " + _EARN
        if status >= 400:
            return False, f"[pwm] charge failed (HTTP {status})"
        return True, ""

    @classmethod
    def from_env(cls) -> "PwmGate":
        token = os.environ.get("PWM_TOKEN") or os.environ.get("PWM_ONBOARD_TOKEN")
        base = (os.environ.get("PWM_BASE") or os.environ.get("PWM_ONBOARD_BASE")
                or "https://physicsworldmodel.org")
        enabled = _truthy(os.environ.get("AI4SCIENCE_PWM_GATE")) and bool(token)
        return cls(token=token, base=base, enabled=enabled)
```

- [ ] **Step 4: Run → PASS** (8 passed).

- [ ] **Step 5: Commit**

```bash
git add ai4science/harness/pwm_gate.py tests/test_harness_pwm_gate.py
git commit -m "feat(pwm-gate): PwmGate — check balance + charge /spend (off-chain ledger, env-gated)"
```

---

## Task 2: wire the gate into the REPL turn loop

**Files:**
- Modify: `ai4science/harness/repl.py`
- Test: `tests/test_harness_pwm_gate_meter.py`

**Context:** `run_common_repl` has `turn_tokens = {"total": 0}` and `_make_wrapped_meter(b, m)` (repl.py ~297) which accumulates tokens. The turn loop calls `_do_turn()` which runs `session.run_turn`. We (1) extend the wrapped meter to also accumulate the turn's PWM + provider wallet, (2) build `PwmGate.from_env()` once, (3) `check()` before the turn (skip on block), (4) `charge()` after.

- [ ] **Step 1: Write the failing test (the meter accumulates PWM + wallet)**

```python
# tests/test_harness_pwm_gate_meter.py
from ai4science.harness import repl


def test_turn_cost_from_usage(monkeypatch):
    # _turn_cost_for(backend, model, usage) returns (pwm, wallet) using the real pricing path.
    from ai4science.harness.events import Usage
    monkeypatch.setattr(repl.routing, "_select_source",
                        lambda backend: ("src", "pid", "0xWALLET", 1.0))
    monkeypatch.setattr(repl.pricing, "price_call",
                        lambda model, usage, price_multiplier=1.0: {"pwm": 0.02, "usd": 0.1})
    pwm, wallet = repl._turn_cost_for("openai", "gpt-5.5",
                                      Usage(input=10, output=5, total=15))
    assert pwm == 0.02 and wallet == "0xWALLET"
```

- [ ] **Step 2: Run → FAIL** (`AttributeError: ... _turn_cost_for`).

- [ ] **Step 3: Implement in `repl.py`**

3a. Add imports near the top (with the other harness imports):
```python
from ai4science.harness.pwm_gate import PwmGate
from ai4science.llm import routing, pricing
```
(If `routing` is already imported, don't duplicate; add only what's missing — verify the existing imports first.)

3b. Add a module-level helper (next to the other `_` helpers):
```python
def _turn_cost_for(backend: str, model: str, usage):
    """(pwm, wallet) for one Usage — the same pricing path make_meter uses."""
    try:
        _src, _pid, wallet, mult = routing._select_source(backend)
        u = {"input": usage.input, "output": usage.output, "total": usage.total}
        cost = pricing.price_call(model, u, price_multiplier=mult)
        return float(cost.get("pwm") or 0.0), wallet
    except Exception:
        return 0.0, None
```

3c. In `run_common_repl`, where `turn_tokens = {"total": 0}` is defined, add a turn-cost accumulator and build the gate:
```python
    turn_cost = {"pwm": 0.0, "wallet": None}
    gate = PwmGate.from_env()
    turn_counter = {"n": 0}
```

3d. In `_make_wrapped_meter`, accumulate PWM + wallet too. Find the wrapped meter body (it does `turn_tokens["total"] += ...; real(u)`) and add:
```python
            pwm, wallet = _turn_cost_for(b, m, u)
            turn_cost["pwm"] += pwm
            if wallet:
                turn_cost["wallet"] = wallet
```

3e. Banner: after the existing mode banner print, add (only when the gate is enabled):
```python
    if gate.enabled:
        print("[harness] PWM gate ON — each turn is charged to the provider in PWM", flush=True)
```

3f. In the turn loop, gate the turn. Find where `_do_turn()` is called (inside the `try:`). BEFORE running the turn, add the check; reset `turn_cost`; AFTER the turn, charge. Concretely, wrap the normal-turn block:
```python
        # PWM gate: block when out of earned PWM.
        allowed, reason = gate.check()
        if not allowed:
            print(reason, flush=True)
            continue
        turn_cost["pwm"] = 0.0
        turn_cost["wallet"] = None
        turn_counter["n"] += 1

        # ... existing: text, images = mentions.expand(...) ; def _do_turn(): ... ; try: _do_turn() except ...

        # AFTER a successful/attempted turn, charge the metered PWM:
        ok, creason = gate.charge(turn_cost["pwm"], turn_cost["wallet"],
                                  purpose=f"ai4science:{active_spec.name}:{active_model}",
                                  idempotency_key=f"{_sid}:{turn_counter['n']}")
        if not ok:
            print(creason, flush=True)
```
(Place the `gate.check()` + reset BEFORE the `text, images = mentions.expand(...)` line, and the `gate.charge(...)` AFTER the existing try/except that runs `_do_turn()`. Keep all existing turn logic intact — only add the check before and the charge after. `active_spec` and `active_model` and `_sid` are in scope.)

- [ ] **Step 4: Run → PASS.** `PYTHONPATH=$(pwd) python3 -m pytest tests/test_harness_pwm_gate_meter.py tests/test_harness_repl_modes.py -v`

- [ ] **Step 5: Full suite + commit**

Run `PYTHONPATH=$(pwd) python3 -m pytest -q` — only the 2 pre-existing failures; the gate is disabled by default so no behavioral regression. Then:
```bash
git add ai4science/harness/repl.py tests/test_harness_pwm_gate_meter.py
git commit -m "feat(pwm-gate): wire gate into REPL — check before turn, charge metered PWM after"
```

---

## Task 3: docs + live check (gate off by default)

**Files:** Modify `docs/CLAUDE_CODE_PARITY.md`.

- [ ] **Step 1: Full suite green (minus the 2 pre-existing).**
- [ ] **Step 2: Live check (controller): gate OFF by default → agent runs normally.**
```bash
WS=$(mktemp -d)
printf 'say READY in one word\n/exit\n' | PYTHONPATH=$(pwd) ai4science chat --mode common --workspace "$WS" 2>&1 | tail -6
# Expect: no PWM-gate banner, runs normally (gate disabled without AI4SCIENCE_PWM_GATE).
```
Also confirm the gate logic blocks when enabled+broke: a unit-level check is enough (Task 1 covers it); do NOT hit the real ledger.
- [ ] **Step 3: Docs.** In `docs/CLAUDE_CODE_PARITY.md`, add "### PWM usage gate" (~10 lines): no free tier — every agent turn costs PWM; the gate checks the user's earned PWM balance (`/balance`) before a turn and blocks with an "earn PWM by contributing" message at ≤0, then debits the metered per-turn PWM to the provider wallet via `/spend` (402-aware, idempotent) after; PWM is earned only by contributing (mining + project contributions), never sold; enabled via `AI4SCIENCE_PWM_GATE` + `PWM_TOKEN` (off by default for dev). Match the doc tone.
- [ ] **Step 4: Commit.**
```bash
git add docs/CLAUDE_CODE_PARITY.md
git commit -m "docs(pwm-gate): document the no-free-tier PWM usage gate"
```

---

## After all tasks
1. Controller verifies every changed file against disk (not subagent reports).
2. Final whole-implementation review (focus: gate disabled-by-default = no regression; charge only fires when enabled; no token leakage; the check blocks at ≤0).
3. `superpowers:finishing-a-development-branch` → merge to main, push.
4. Update memory `project_pwm_economic_model.md` → usage gate built.
5. Follow-ups: surface remaining balance in `/cost`; a pre-turn affordability estimate; on-chain settlement via the M6 relayer.
