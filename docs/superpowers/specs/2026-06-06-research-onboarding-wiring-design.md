# Research-Mode Onboarding Wiring (Design Spec)

**Date:** 2026-06-06
**Status:** Approved for planning
**Relationship:** Makes the AI4Science **research (science-tier) agent** the "UX layer" that §3 of the PWM Easy-Onboarding plan (`pwm/pwm-team/plan/easy_onboarding/plan.md`) names it to be: help the user author a valid artifact → submit it → the platform runs the S1–S4 quality gate → the user earns PWM. Builds on the agent framework + the moat (science-tier only). On-chain promotion (M6 relay/payer) is **out of scope** — this wires the LIVE off-chain loop.

---

## 1. Overview

Add an **`onboarding` capability bundle** (a new `ai4science/harness/onboard_tools.py`) registered in `capabilities.py` and added to the **research** agent's capabilities. Four tools wrap the live `pwm_nonprofit` HTTP API:

1. **`onboard_guide(artifact_type)`** — returns the required fields + a short how-to for a `principle` / `digital-twin` / `benchmark` / `solution`, so the agent authors a *valid* bundle (grounding it with the `pwm-data` tools research already has). Local, no network.
2. **`onboard_submit(artifact_type, fields, confirm=False)`** — validates the fields against the type's schema, then POSTs to `/api/v1/pwm-submit/{type}` with the user's `pwm_…` API key. **Strict-boolean confirm-guard** (preview unless `confirm is True`) because it writes to the live platform and triggers the S1–S4 gate + reward.
3. **`onboard_status()`** — `GET /api/v1/pwm-token/transactions` → recent ledger entries (the reliable ACCEPT-reward trail).
4. **`onboard_balance()`** — `GET /api/v1/pwm-token/balance` → total PWM earned + caps.

**Auth (solved):** the backend (`auth/dependencies.py`) accepts a personal API key (`pwm_…` prefix) as `Authorization: Bearer <key>`. The user supplies it via env `PWM_ONBOARD_TOKEN`; the agent acts as that user. No browser session needed.

**Config:** `PWM_ONBOARD_BASE` (default `https://physicsworldmodel.org`) + `PWM_ONBOARD_TOKEN`. When the token is unset, `onboard_guide` and the `onboard_submit` **preview** still work; the write/read calls return a clear "set `PWM_ONBOARD_TOKEN`" message (graceful, like the cassi tools).

**Moat:** onboarding is **science-tier** — research (and any future science agent that lists it) gets it; common mode cannot reach it.

**The §3 flow research mode now drives end-to-end:** ground in the registry (`pwm_principles`/`pwm_benchmarks`/`pwm_solutions`) → author a bundle → optionally pre-check with the existing `pwm_validate`/`pwm_judge_cassi` → `onboard_submit(confirm=True)` → server runs S1–S4 → `onboard_balance`/`onboard_status` show the 0.1 PWM.

---

## 2. The live API contract (verified from `pwm_nonprofit`)

**Submit (Form POST, returns HTML confirm page with the submission + status badge):**
- `POST /api/v1/pwm-submit/principle` — `name, domain, rule, formula, reference`
- `POST /api/v1/pwm-submit/spec` (**digital-twin**) — `principle_id, operator_type, omega_description, epsilon, reference`
- `POST /api/v1/pwm-submit/benchmark` — `spec_id, tier, dataset_description, metric, metric_threshold, dataset_url`(optional)
- `POST /api/v1/pwm-submit/solution` — `principle_id, ai_system, task_description, artifact_description, self_reported_metric`(optional)

**Ledger (JSON, `get_current_user` → Bearer key):**
- `GET /api/v1/pwm-token/balance` → `{"success": true, ...balance}`
- `GET /api/v1/pwm-token/transactions?limit=&offset=` → `{"success": true, "transactions": [...]}`

The submit endpoints render HTML (server-side UI), so `onboard_submit` reports a **best-effort** status from the response (HTTP ok + a status-badge regex) and points the user to `onboard_status`/`onboard_balance` (clean JSON) for the authoritative ACCEPT-reward signal. *(A small JSON `GET /api/v1/pwm-submit/status/{id}` on the backend would make this crisp — noted as a backend follow-up, out of scope here.)*

`type → endpoint` map: `{"principle":"principle","digital-twin":"spec","benchmark":"benchmark","solution":"solution"}`.

---

## 3. Components & Files

### 3.1 `ai4science/harness/onboard_tools.py` (new)
- **Field schema** (embedded, from §2): `REQUIRED_FIELDS: dict[type -> (required tuple, optional tuple)]` and a one-line how-to per type.
- **`_base()`** = env `PWM_ONBOARD_BASE` or `https://physicsworldmodel.org` (rstrip `/`).
- **`_token()`** = env `PWM_ONBOARD_TOKEN` (or None).
- **HTTP helpers** (urllib, self-contained): `_post_form(path, fields) -> (status_code, text)` with `Authorization: Bearer` + `Content-Type: application/x-www-form-urlencoded`; `_get_json(path) -> dict` with Bearer.
- **`onboard_tools() -> list[Tool]`** returning the 4 tools (all `mutating=False`; errors → `"[onboard error] ..."`):
  - `onboard_guide`: `{artifact_type}` → required+optional fields + how-to (local).
  - `onboard_submit`: `{artifact_type (enum), fields (object), confirm (bool)}` →
    `confirm = confirm is True`; validate type + that all required fields present (missing → `[onboard error] missing fields: ...`); if no token → `[onboard error] set PWM_ONBOARD_TOKEN ...`; if not confirm → **preview** (type, endpoint, the fields, "Pass confirm=true to submit to the live platform; it runs the S1–S4 gate and may award PWM."); if confirm → `_post_form` → report status (ok + best-effort badge) + "check onboard_status / onboard_balance".
  - `onboard_status`: no token → message; else `_get_json("/api/v1/pwm-token/transactions?limit=20")` → compact list (kind, amount, status, time), json-truncated.
  - `onboard_balance`: no token → message; else `_get_json("/api/v1/pwm-token/balance")` → balance + caps.

### 3.2 `ai4science/harness/agents/capabilities.py` (modify)
Add `_onboarding(ctx)` provider (lazy import `onboard_tools`) + register `"onboarding"` in `CAPABILITY_BUNDLES`.

### 3.3 `ai4science/harness/agents/specs/research.py` (modify)
Add `"onboarding"` to `capabilities` → `("pwm-actions", "pwm-data", "onboarding")`. Extend `RESEARCH_PROMPT` with a short onboarding steer: "You can help a contributor put an artifact on PWM and earn PWM: author a valid principle/digital-twin/benchmark/solution (use `onboard_guide` for the fields and the `pwm_*` tools to ground), pre-check it, then `onboard_submit` (it previews first — pass confirm=true to actually submit to the live platform; the server runs the S1–S4 gate and awards PWM on accept). Use `onboard_status`/`onboard_balance` to track the reward. Always preview before submitting."

---

## 4. Data Flow

```
research mode (science-tier)
  pwm_principles/pwm_benchmarks/pwm_solutions   # ground in the registry
  onboard_guide("solution")                     # required fields for a solution
  ... agent authors the bundle, pre-checks with pwm_validate/pwm_judge_cassi ...
  onboard_submit("solution", {fields}, confirm=false)  # PREVIEW (no write)
  onboard_submit("solution", {fields}, confirm=true)   # POST -> server S1-S4 gate
  onboard_status() / onboard_balance()          # ACCEPT -> 0.1 PWM in the ledger
```

---

## 5. Error Handling

| Failure | Behavior |
|---|---|
| Unknown `artifact_type` | `[onboard error] unknown type; one of principle/digital-twin/benchmark/solution` |
| `onboard_submit` missing required fields | `[onboard error] missing fields: ...` (no POST) |
| No `PWM_ONBOARD_TOKEN` on submit/status/balance | `[onboard error] set PWM_ONBOARD_TOKEN (your pwm_… API key from physicsworldmodel.org)` |
| `onboard_submit` without `confirm` | preview (no POST) |
| HTTP error (401/4xx/5xx, network) | `[onboard error] <status/reason>` (the turn continues) |

---

## 6. Testing (TDD)

- **`onboard_guide`:** each type returns its required+optional fields; unknown type → error. (Local, no network.)
- **`onboard_submit` validation/guard:** missing required field → `[onboard error] missing fields`, no POST; no token → token message, no POST; `confirm=false`/`"false"`/`"true"` → **preview**, no POST (monkeypatch `_post_form` to raise); `confirm=True` → calls `_post_form` with the right path + form fields + Bearer (monkeypatched) → reports success. Strict-boolean guard (string can't submit).
- **`onboard_status`/`onboard_balance`:** monkeypatch `_get_json` → formats the ledger/balance; no token → message.
- **Integration:** `capabilities.CAPABILITY_BUNDLES` has `"onboarding"`; `resolve_capability("onboarding", ctx)` returns the 4 tools; the `research` spec lists `"onboarding"`; `build_registry_for(research)` includes the 4 `onboard_*` tools; **common does NOT** (moat). Framework/moat tests still pass.
- **Live E2E (controller):** exercise the SAFE paths only — `/mode research`, `onboard_guide`, `onboard_submit(..., confirm omitted)` **preview**, and the no-token graceful message. **Do NOT perform a real production submit** (that creates a real submission + reward on the live platform — the user runs that with their own key).

---

## 7. Out of Scope

- **On-chain promotion (M6 / Stage 0.5):** the `PWMRegistrar` relay, registrar/payer hot keys, Base settlement. This wires only the LIVE off-chain author→submit→gate→reward loop.
- **A JSON submission-status endpoint** on the `pwm_nonprofit` backend (would make `onboard_status` per-submission crisp; current status uses the ledger trail). Noted backend follow-up.
- **Authoring automation beyond guidance** — the agent composes the bundle from the user's intent + `onboard_guide`; we don't add a separate authoring engine.
- **Real production submit in CI / our own verification** — token-gated + confirm-guarded so it can't fire accidentally.
