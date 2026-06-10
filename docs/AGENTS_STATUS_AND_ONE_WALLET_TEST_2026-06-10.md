# All Six Agents — Status & One‑Wallet Test (2026‑06‑10)

Snapshot answer to: *"Have you finished all of these agents — unified‑LLM,
research, paper, claude‑code, codex, computational‑imaging? How can I use one
wallet address to test them?"*

**Yes — all six are finished, wired, and verified end‑to‑end.**

---

## 1. Status — verified charge + earn per agent

| Agent | Spec | Pool (PWM) | Verified charge | Verified earn (75%) |
|---|---|---|---|---|
| unified‑LLM | `ai4science/harness/agents/specs/unified_llm.py` | 480,000 | ✅ 0.002185 | ✅ 18,000 |
| research | `ai4science/harness/agents/specs/research.py` | 600,000 | ✅ 0.004721 | ✅ 22,500 |
| paper | `ai4science/harness/agents/specs/paper.py` | 480,000 | ✅ 0.003236 | ✅ 18,000 |
| claude‑code | `ai4science/harness/agents/specs/claude_code.py` | 520,000 | ✅ 0.002185 | ✅ 19,500 |
| codex | `ai4science/harness/agents/specs/codex.py` | 520,000 | ✅ 7e‑05 *(after token fix)* | ✅ 19,500 |
| computational‑imaging | `ai4science/harness/agents/specs/computational_imaging.py` | **1,400,000** (largest) | ✅ 0.005123 | ✅ **52,500** |

- All six registered in the harness agent registry; PWM gate, usage hook, and
  `/feedback` plumbing live for every one.
- Production (physicsworldmodel.org) has the agent‑pool API deployed for all
  six (pools respond; `m_solo 0.0, seeded:false` — emission held until
  post‑audit per the genesis greenlight directive).
- Verified one‑wallet run result: the single test wallet **paid** PWM on every
  agent and **earned 150,100 PWM lifetime** across the six pools
  (computational‑imaging largest at 52,500).
- **Agent improvement is the primary user earning track** (feedback time-decay
  + usage-weighted contributions, one `A_k` formula; can out-earn website
  mining by orders of magnitude): `docs/AGENT_IMPROVEMENT_EARNING_METHOD.md`.

### Model lineup (directive 2026‑06‑10): Fable 5 leads
All agents that routed to Opus 4.8 now lead with **`claude-fable-5`**
(orchestration + checking chains, repl default, pricing at Opus‑tier $15/$75
per M until an official list price lands); **`claude-opus-4-8`** moves to the
fallback slot (Opus 4.7's old role — the 4.7 pricing row was dropped, 4.6 had
no remaining references). Chain: Fable 5 → Opus 4.8 → Sonnet 4.6 → GPT‑5.5 →
Gemini. AI4Science commit `82dc980`; **verified live on prod** — turn served
and billed as `ai4science:unified-LLM:claude-fable-5` (0.002501 PWM). The
charge column above reflects the Opus 4.8 runs; per‑turn costs on Fable 5 are
within ~15% at the same price tier. Open item: confirm Fable 5 list price
(`pricing.py:23`).

### codex note (fixed 2026‑06‑09)
codex initially billed **0.0**: the ChatGPT/codex access token (~10‑day life,
only refreshed by a live CLI call) had expired → silent 401. Fixed three ways:

1. Token refreshed (`codex exec`) → codex bills correctly (≈7e‑05/turn).
2. Code hardened: `codex_token_expired()` + a clear "login expired — refresh"
   adapter message instead of a silent zero (commit `43164af`).
3. Weekly keepalive systemd timer (`deploy/codex-keepalive.{service,timer}`,
   Mon 03:30 UTC, Persistent) keeps the login fresh (commit `11c43a8`;
   documented in pwm_nonprofit `deploy/AGENT_MINING_ROLLOUT.md` §1a).

---

## 2. Test all six with ONE wallet

Full operate‑it‑yourself guide: **`docs/TEST_AGENTS_WITH_ONE_WALLET.md`**.

### One command (recommended)

On a box with the founder LLM providers configured (the agent host):

```bash
cd <AI4Science repo>
scripts/test_agents_mining.sh 0x7E57000000000000000000000000000000000001
#   (omit the arg → default test wallet; or pass your own 0x…)
```

What it does: spins up the real backend on SQLite → binds **one account ↔ one
wallet** → funds 100 PWM → for EACH agent runs a real gated LLM turn (**pays**
PWM to the provider) + `/feedback` (**registers an earning contribution**) →
emits one weekly epoch → reports → cleans up.

Expected shape of the result:

```
unified-LLM            charged 0.0022 PWM   feedback submitted
research               charged 0.0047 PWM   feedback submitted
paper                  charged 0.0032 PWM   feedback submitted
claude-code            charged 0.0022 PWM   feedback submitted
codex                  charged ~7e-05 PWM   feedback submitted
computational-imaging  charged 0.0051 PWM   feedback submitted
...
computational-imaging       70000.0    52500.0   ← largest pool
wallet 0x7E57…0001  lifetime_earned 150,100.00 PWM
```

### Against a remote/staging backend

```bash
scripts/test_agents_mining.sh 0xYOURWALLET \
  --backend https://staging.example \
  --admin-token <admin key/JWT>        # or env PWM_ADMIN_TOKEN
```

⚠️ This funds an account, seeds pools, and **emits a real epoch** on the target
backend. Do **not** point it at production — for prod, use the charge‑only
verification below.

### Prod charge‑only verification (Option A)

One gated turn per agent against `https://physicsworldmodel.org` using a real
**user** `PWM_TOKEN` — debits a few millionths of real PWM, **no admin / fund /
seed / emit**, so the emission hold stays intact:

```bash
export AI4SCIENCE_PWM_GATE=1 PWM_BASE=https://physicsworldmodel.org PWM_TOKEN=<your pwm_ key/JWT>
for a in unified-LLM research paper claude-code codex computational-imaging; do
  printf 'reply DONE\n' | ai4science chat --mode "$a" --workspace /tmp --yes
done
```

Getting the token is now one command — `ai4science login --pwm` (browser
approval; stores a revocable key, never a private key; the gate picks it up
automatically). The account must hold some PWM. *(Status: DONE 2026-06-10 —
verified live with wallet `0xe550…94a74`: turn charged 0.002185 PWM with the
90/10 split, `/feedback` contribution registered. See pwm repo
`pwm-team/doc/PWM_AI4SCIENCE_LOGIN_PWM_LIVE_TEST_2026-06-10.md`.)*

### Manual hop‑by‑hop

Section B of `docs/TEST_AGENTS_WITH_ONE_WALLET.md`: bind wallet → set
`AI4SCIENCE_PWM_GATE=1 PWM_TOKEN=<key>` → run each
`ai4science chat --mode <agent>` → POST `run-epoch` [admin] → check
`/pwm-token/balance` + `/agent-pool/<agent>/leaderboard`.

---

## 3. Prerequisites & safety

- `claude-code` needs an Anthropic (Claude Code) login on the host; `codex`
  needs a ChatGPT/codex login (kept fresh by the weekly keepalive timer). The
  wallet is billing only — the founder provides the LLM.
- The whole charge/earn loop is **off by default**: it only engages when
  `AI4SCIENCE_PWM_GATE=1` AND a `PWM_TOKEN` are set. Dev/CI stay free.
- One wallet/token covers all six agents — no per‑agent credentials.
