# Agent-Improvement PWM Earning Method

*The single formula behind all agent-improvement rewards (feedback included),
as implemented and live. (2026-06-10)*

## 1. The formula — one per agent, per weekly epoch

```
A_k = (M_pool − M(t)) × w_k / Σ(w_j over active contributions j)    × λ
```

- **M_pool** — that agent's own pool. Total 4,000,000 PWM across the six:
  computational-imaging 1,400,000 (largest) · research 600,000 · codex 520,000
  · claude-code 520,000 · paper 480,000 · unified-LLM 480,000.
- **M(t)** — what the pool has already minted, DERIVED from the ledger
  (Σ `agent_emission` + `agent_treasury_emission` txns tagged with the agent)
  — no separate counter to drift.
- **w_k** — the contribution's weight (§2).
- **λ = 0.05** — weekly release rate: each epoch emits 5% of what REMAINS, so
  the pool never exhausts and early epochs pay more (Zeno decay). unified-LLM
  epoch-1 budget 24,000 → epoch-10 ≈15,100 → epoch-50 ≈1,950.
- Epochs are ISO weeks (`2026-W25`) and idempotent per (agent, epoch,
  contribution) — re-running the cron cannot double-pay.

## 2. What counts as agent improvement — and how w_k is set

| Type | How you earn it | w_k rule |
|---|---|---|
| **feedback** | `/feedback <problem/suggestion>` while using the agent | **Frozen at submission (time-decay)**: `10/(1 + 0.1×agent_total_usage_at_submission) × quality`. First usage locks 10 forever; after ~1,000 turns locks ≈0.1. **Usage-ladder unlock (directive 2026-06-10):** the n‑th feedback requires the user's own paid turns on that agent — 20 for the 1st, +19 for the 2nd, … floor +5 (`feedback_turns_cumulative`); zero-usage submissions return `need_more_usage` and earn nothing. Repeatable per rung; no head-count cap. |
| **tool** | a domain tool the agent invokes in paid turns | **Usage-weighted**: Σ weight_units per DISTINCT non-author user (self-usage excluded; optional per-user sybil cap) × quality |
| **solution** | e.g. a CASSI solver dispatched by computational-imaging (`cassi_dispatch` auto-attributes) | same usage-weighted rule |
| **digital_twin / benchmark** | forward models / tasks the agent runs against | same usage-weighted rule |

Two tracks, one formula:
- **Feedback = time-decay bootstrap** — rewards being EARLY; sustains the first
  users' usage, tapers to a nudge ("contribute or mine") for later users.
- **Tools/solutions = usage track** — rewards being USEFUL, forever: every paid
  turn that touches your contribution adds weight, week after week.

## 3. Payout split — automatic, no claim step

Each epoch, every active contribution with w_k > 0 receives its A_k:
- **75% → author's account** (bound to their wallet address)
- **25% → treasury** (verifier slice, `VERIFIER_BPS=2500`)
Both legs count toward M(t), so the slice draws down the pool honestly.
Accounts settle on-chain (PWM ERC-20 on Base) on the weekly settlement batch.

## 4. Worked examples (epoch-1, unified-LLM, verified live)

Single feedback contributor, fresh pool:
```
remaining = 480,000 − 0      budget = 0.05 × 480,000 = 24,000
Σw = 10 (only contribution)  A_k = 24,000 × 10/10 = 24,000
→ author 18,000 (75%) · treasury 6,000
```
This is exactly the verified one-wallet harness output
(`unified-LLM A_k 24000.0 → wallet 18000.0`; six pools → 150,100 lifetime).

With competition — early feedback w=10 vs. a popular tool w=30:
```
Σw = 40 → feedback author: 24,000 × 10/40 × 0.75 = 4,500
          tool author:     24,000 × 30/40 × 0.75 = 13,500
```

## 5. Implementation map

- Math (read-only): `pwm_nonprofit/services/agent_emission.py`
  (`compute_agent_emission`, `agent_minted`, `current_epoch_id`)
- Writes: `pwm_nonprofit/services/pwm_token_service.py`
  (`emit_agent_epoch`, `emit_all_agents`, `recompute_weights`,
  `submit_feedback` — freeze-at-submission, `record_usage`)
- Config (locked): `pwm_nonprofit/services/agent_pool_config.py`
  (`POOL_SHARES`, `EMISSION_LAMBDA=0.05`, `VERIFIER_BPS=2500`,
  `FEEDBACK_BASE=10`, `FEEDBACK_DECAY=0.1`, `FEEDBACK_FIRST_N_USERS=0`)
- API: `POST /api/v1/agent-pool/{agent}/feedback` [user] ·
  `GET /{agent}/pool` · `GET /{agent}/leaderboard` ·
  `POST /run-epoch` [admin] · `GET /settlements` [admin]
- Cadence: `pwm-agent-epoch.timer` Mon 00:10 UTC (first epoch fires when the
  reward pool goes live, expected late June 2026)

Related docs: user manual `PWM_AI4SCIENCE_USER_MANUAL_2026-06-10.md` ·
spec `pwm-team/plan/PWM_AGENT_MINING_SPEC_E0_E1_2026-06-07.md` ·
live test `PWM_AI4SCIENCE_LOGIN_PWM_LIVE_TEST_2026-06-10.md`.
