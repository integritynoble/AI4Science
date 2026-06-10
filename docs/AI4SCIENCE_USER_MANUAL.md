# AI4Science User Manual

*How to get your first PWM, run the six agents, and earn while you use them.*
*(2026-06-10)*

AI4Science is a Claude-Code-style agent for science. You pay for usage in
**PWM** (the Physics World Model token) — not with API keys, not with a credit
card. The LLMs (Claude, GPT, Gemini, …) are served by the founder provider
accounts; your PWM balance on **physicsworldmodel.org** is debited a few
*thousandths* of a PWM per turn.

**The loop in one line:**

> **Mine your first PWM on the website → log the CLI in with one browser
> approval → use the agents → improve them (feedback, tools, solutions) →
> PWM flows back to you automatically.**

**Where the real earning is:** website mining pays **0.1–5 PWM per artifact**
— it bootstraps you. **Improving the agents is the
primary track:** feedback instantly refunds (roughly) your next block of usage
while an agent is young, and contributed tools/solutions earn weekly from
4,000,000 PWM of agent pools for as long as others use them — which can
out-earn website mining by orders of magnitude (full math:
`AGENT_IMPROVEMENT_EARNING_METHOD.md`).

Your wallet **private key is never needed and never asked for** — anywhere.
If anything ever asks you for it, it is not us. (Why this is safe:
`PWM_LEDGER_SAFETY_AND_ONCHAIN_SETTLEMENT_QA_2026-06-10.md` in the pwm repo.)

---

## Step 1 — Mine your first PWM on physicsworldmodel.org (the bootstrap)

Everyone starts here — but note this is the *bootstrap*, not the main earning
track (that's improving the agents, Steps 4–5). PWM is **earned by
contributing physics**, on
[https://physicsworldmodel.org](https://physicsworldmodel.org):

1. **Create an account** — sign in with your wallet (SIWE: your wallet signs a
   login challenge in your browser; the key never leaves it) or with
   email + password, then bind your wallet address on the account page. The
   address is where your earnings ultimately settle on-chain.
2. **Submit one of the four artifact types** (site forms, or the `/cli`
   browser terminal which includes free drafting assistance):
   - **Principle** — a physical law/identity with its falsifiable statement
   - **Digital Twin** — a forward model of a real instrument/setup
   - **Benchmark** — a task with data + metric on a digital twin
   - **Solution** — an algorithm that solves a benchmark
3. **Review → award.** Accepted submissions are awarded PWM automatically to
   your account (typically **0.1–5 PWM** depending on artifact type and
   quality).

**One accepted artifact funds hundreds of agent turns** — a typical turn costs
0.002–0.005 PWM, so even 0.1 PWM ≈ 20–50 turns; 5 PWM ≈ a thousand or more.

## Step 2 — Connect the CLI (one browser approval, no keys)

Install and log in:

```bash
pip install pwm-ai4science          # installs the `ai4science` command
ai4science login --pwm              # device-flow login
```

`login --pwm` prints a short code and opens
`https://physicsworldmodel.org/cli-auth?code=XXXX-XXXX`. Log in there (if you
aren't already), check the code matches your terminal, click **Approve**. The
CLI receives a **revocable API key** — never your password, never your wallet
key — and stores it at `~/.config/ai4science/pwm_account.json` (permissions
0600).

```bash
ai4science whoami                   # shows your account + bound wallet
export AI4SCIENCE_PWM_GATE=1        # turn billing on (off by default)
```

To disconnect: `ai4science logout` (and revoke the key on your account page).

## Step 3 — Use the agents

Six agents, one balance, one command:

```bash
ai4science chat --mode <agent>
```

| Agent (`--mode`) | What it does | ~PWM/turn |
|---|---|---|
| `unified-LLM` | General assistant across Claude / GPT / Gemini (switch with `/model`) | ~0.002 |
| `research` | Science research harness with read-only access to the PWM registry & solutions | ~0.005 |
| `paper` | Deterministic peer-review panel (3 reviewers + area chair) → review bundle | ~0.003 |
| `claude-code` | The Claude Code coding agent | ~0.002 |
| `codex` | The OpenAI Codex coding agent | ~0.0001 |
| `computational-imaging` | CASSI/imaging specialist: forward checks, GPU dispatch, result evaluation | ~0.005 |

Anthropic-backed turns are served by **Claude Fable 5** first (fallback chain:
Fable 5 → Opus 4.8 → Sonnet 4.6 → GPT-5.5 → Gemini). Inside a chat, `/mode`
switches agents and `/model` switches LLM brands.

Every turn debits your ledger and is split **90% to the LLM provider / 10% to
the mining pool** — all visible in your transaction history.

## Step 4 — Earn while you use: feedback sustains your usage

**The sustenance loop.** Use an agent, then tell us what you found — each
accepted `/feedback` pays an **instant PWM reward sized to roughly fund your
next block of usage**:

```
/feedback the dispatch step was confusing — suggest showing the queue position
```

How it works, end to end:

- **The ladder:** the n‑th feedback on an agent unlocks after your own paid
  turns on it — **20 turns for the first, 19 more for the second, … down to a
  5‑turn floor**. Submitting early returns `need_more_usage` and earns nothing
  (feedback PWM is for genuine users, not drive‑by claims).
- **The reward — instant, automatic, no claim step:**
  `reward = next_block_turns × your own average turn cost × decay`, where
  `decay = 1/(1 + 0.1 × agent_total_usage)`. Early in an agent's life decay ≈
  1.0, so your feedback roughly **refunds your next 19, 18, … turns** — early
  users keep using agents nearly for free.
- **The decay is the design:** as the agent accumulates usage the multiplier
  falls toward 0 — late feedback pays a fraction of a turn and **won't sustain
  usage**. That's the signal to move to contributing or mining (Step 5).
- Feedback is recorded against your wallet (governance can mark down spam),
  but it takes **no share of the weekly pool epochs** — the big `A_k` emission
  from the 4M PWM pools is reserved for **usage‑weighted contributions**
  (tools, solutions — Step 5).

What good feedback looks like: a problem you actually hit, a confusing step, a
missing capability, a concrete suggestion.

> **In short: use an agent ~20 turns → feedback → your next block of usage is
> roughly refunded → repeat, with shrinking blocks.** Early users ride this
> loop almost for free; later users' rewards taper below their costs — by
> design — and the real earning shifts to contributed tools/solutions (or
> mining).

## Step 5 — Earning later, once feedback rewards have decayed

As the agents accumulate usage, the feedback multiplier decays and rewards stop
covering your turn costs. Keep earning by:

1. **Improve the agents with registered contributions** — THE main earning
   track. Contribute a tool, solution, or dataset to an agent (e.g. a CASSI
   solver to computational-imaging); every paid turn that *uses* it adds
   usage-weight, and you earn from that agent's pool **every week it keeps
   being used** — usage-weighted, not first-come, and it scales with the
   agent's success (same `A_k` formula as feedback; see
   `AGENT_IMPROVEMENT_EARNING_METHOD.md`).
2. **Weekly wins** — benchmark competitions and weekly challenge rewards on
   the site.
3. **Mining on [physicsworldmodel.org](https://physicsworldmodel.org)** — more
   principles, digital twins, benchmarks, solutions (the bootstrap path never
   closes).
4. **Compute provision** — serve GPU jobs for the compute loop and earn the
   provider side of the 90/10 split.

## The agent-improvement earning method (the math)

Everything in Steps 4–5 is one formula, applied per agent, per weekly epoch:

```
A_k = (M_pool − M(t)) × w_k / Σ(w_j over active contributions j)    × λ
```

- **M_pool** — that agent's own pool:

  | Agent | Pool (PWM) |
  |---|---|
  | computational-imaging | **1,400,000** (largest) |
  | research | 600,000 |
  | codex | 520,000 |
  | claude-code | 520,000 |
  | paper | 480,000 |
  | unified-LLM | 480,000 |
  | **Total** | **4,000,000** |

- **M(t)** — what that pool has already paid out (derived from the ledger, so
  it can't drift).
- **λ = 0.05** — each week emits 5% of what *remains*: the pool never runs
  out, and **early epochs pay more** (unified-LLM epoch-1 budget 24,000 →
  epoch-10 ≈15,100 → epoch-50 ≈1,950).
- **w_k** — your contribution's weight. This is where the two tracks differ:

  | Improvement type | w_k rule |
  |---|---|
  | **feedback** (`/feedback` in chat) | **Not part of A_k** — paid **instantly** at submission, sized to your next usage block: `next_block_turns × your avg turn cost × 1/(1 + 0.1 × agent_usage)`. **Unlock ladder:** 20, +19, … (floor +5) of your own paid turns on that agent. |
  | **tool / solution / digital twin / benchmark** (registered, used by agents in paid turns) | **Usage-weighted:** Σ weight_units per *distinct non-author* user × quality (self-usage excluded; sybil-capped). Grows every week others keep using it. |

- **Payout:** each epoch, every active contribution receives its A_k —
  **75% to you** (your wallet-bound account, automatically, no claim step),
  25% to the treasury.

**Worked example** (epoch 1, unified-LLM, fresh pool): your contributed tool
is the only used contribution → `A_k = 0.05 × 480,000 = 24,000` → **you get
18,000 PWM** (75%). With competition — your tool w=30 vs. another author's
solution w=10 → Σw=40 → you get `24,000 × 30/40 × 0.75 = 13,500`, the other
author 4,500. (Feedback is *not* in this race — it is paid instantly and
modestly at submission, Step 4.)

Full implementation map (files, endpoints, config):
`AGENT_IMPROVEMENT_EARNING_METHOD.md`.

## Your earnings → your wallet on-chain

PWM accrues on your site ledger instantly (free, per-action). On the weekly
settlement batch, the treasury sends **real PWM (ERC-20 on Base)** to your
bound wallet address — receiving requires nothing from you, and every batch is
publicly verifiable on BaseScan. Until settlement, your balance is visible at
any time on your account page and via the API.

## Safety rules (the short version)

- **Never share your wallet private key.** Not with ai4science, not with the
  website, not with anyone. Login is browser-approved; spending uses a
  revocable token; receiving needs no key at all.
- The stored CLI token can only spend your *site ledger* balance on agent
  usage. Leaked? Revoke it on the account page — damage stops instantly.
- Billing is **off by default**: nothing charges until you set
  `AI4SCIENCE_PWM_GATE=1` with a logged-in account.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `insufficient PWM (balance 0.000)` | Mine your first PWM (Step 1) — the gate refuses to run on an empty balance. |
| `login expired / could not verify your PWM balance` | `ai4science login --pwm` again (or set `PWM_TOKEN` directly for scripts). |
| Browser shows a different code than the terminal | **Deny it.** Someone else may be phishing an approval; restart `login --pwm`. |
| A turn charged but the agent errored | Charges are per completed turn; transient provider errors are not billed. Check `/model` to switch brands. |
| Want to stop billing immediately | `unset AI4SCIENCE_PWM_GATE` (and/or `ai4science logout`). |

---

*Companion docs:* test process — `TEST_AGENTS_WITH_ONE_WALLET.md` · agents
status — `AGENTS_STATUS_AND_ONE_WALLET_TEST_2026-06-10.md` · live prod test —
pwm repo `pwm-team/doc/PWM_AI4SCIENCE_LOGIN_PWM_LIVE_TEST_2026-06-10.md` ·
safety design — pwm repo
`pwm-team/doc/PWM_LEDGER_SAFETY_AND_ONCHAIN_SETTLEMENT_QA_2026-06-10.md`.
