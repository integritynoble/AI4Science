# Agent-Improvement PWM Earning Method

*Agent-improvement rewards: instant usage-sized feedback + the A_k pool formula,
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
| **feedback** | `/feedback <problem/suggestion>` while using the agent | **Outside A_k — paid INSTANTLY at submission (sustenance, directive 2026-06-10):** `reward = next_block_turns × user's own avg turn cost × 1/(1 + 0.1×agent_total_usage)`. Early ≈ refunds the next 19, 18, … turns; decays toward 0 with agent usage. **Unlocks only on LOW BALANCE** (≤ `FEEDBACK_LOW_WATER_TURNS`≈3 × the user's own capped avg turn cost) after real usage of that agent — never used → `use_agent_first`; healthy balance → `balance_not_low`; each runway must be burned before the next refill. Runway shrinks 19, 18, … floor 5 (`feedback_block_turns`); per-turn cost capped (`FEEDBACK_MAX_TURN_COST`) against spend-inflation. Repeatable per rung; 100% to the user (no treasury slice on these micro-rewards); draws down the pool via the `agent_feedback_reward` txn (counted in M(t)); takes no weekly-epoch share (weight stays 0). |
| **tool** | a domain tool the agent invokes in paid turns | **Usage-weighted**: Σ weight_units per DISTINCT non-author user (self-usage excluded; optional per-user sybil cap) × quality |
| **solution** | e.g. a CASSI solver dispatched by computational-imaging (`cassi_dispatch` auto-attributes) | same usage-weighted rule |
| **digital_twin / benchmark** | forward models / tasks the agent runs against | same usage-weighted rule |

Two tracks, two mechanisms:
- **Feedback = instant sustenance (outside A_k)** — unlocks when a user has
  spent their PWM down to nearly nothing on an agent, and refills a shrinking
  runway (~19 turns, then 18, … floor 5 — the "use your PWM up → feedback
  refills the next, smaller block" metaphor); tapers to a nudge ("contribute
  or mine") as agent usage grows.
- **Tools/solutions = the A_k usage track** — rewards being USEFUL, forever:
  every paid turn that touches your contribution adds weight, and the weekly
  epochs pay `A_k` (75% author / 25% treasury), week after week.

## 3. Payout split — automatic, no claim step

Each epoch, every active contribution with w_k > 0 receives its A_k:
- **75% → author's account** (bound to their wallet address)
- **25% → treasury** (verifier slice, `VERIFIER_BPS=2500`)
Both legs count toward M(t), so the slice draws down the pool honestly.
Accounts settle on-chain (PWM ERC-20 on Base) on the weekly settlement batch.

## 4. Worked examples (epoch-1, unified-LLM, verified live)

A_k (weekly, usage-weighted contributions only) — single used tool, fresh pool:
```
remaining = 480,000 − 0      budget = 0.05 × 480,000 = 24,000
Σw = 30 (only contribution)  A_k = 24,000
→ author 18,000 (75%) · treasury 6,000
```
With competition — your tool w=30 vs. another solution w=10:
```
Σw = 40 → tool author:     24,000 × 30/40 × 0.75 = 13,500
          solution author: 24,000 × 10/40 × 0.75 = 4,500
```

Feedback (instant sustenance, outside A_k) — early user on unified-LLM at
~0.0025 PWM/turn:
```
feedback #1 (balance exhausted): 19 × 0.0025 × ~1.0 ≈ 0.0475 PWM  (refills ~19 turns)
feedback #2 (runway burned):     18 × 0.0025 × ~1.0 ≈ 0.045  PWM
late user (decay 0.01):        5 × 0.0025 × 0.01 ≈ 0.0001 PWM  (won't sustain — contribute or mine)
```
Live-verified (harness, test ladder=1): each feedback refunded almost exactly
the next turn's cost — net balance change per use+feedback cycle ≈ 0.

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
