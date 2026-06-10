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
> approval → use the agents → give feedback → PWM flows back to you
> automatically.**

Your wallet **private key is never needed and never asked for** — anywhere.
If anything ever asks you for it, it is not us. (Why this is safe:
`PWM_LEDGER_SAFETY_AND_ONCHAIN_SETTLEMENT_QA_2026-06-10.md` in the pwm repo.)

---

## Step 1 — Mine your first PWM on physicsworldmodel.org

Everyone starts here. PWM is **earned by contributing physics**, on
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

## Step 4 — Earn while you use: time-decay feedback rewards

**This is the part early users should not miss.** Each agent has its own
PWM mining pool (4,000,000 PWM across the six; computational-imaging's
1,400,000 is the largest). **Anyone, at any time**, can earn from that pool
just by reporting their experience — but the reward per feedback **decays as
the agent's total usage grows**, so the earliest feedback is worth the most:

```
/feedback the dispatch step was confusing — suggest showing the queue position
```

Type `/feedback <your suggestion or problem>` inside any agent chat. That
registers a **feedback contribution** in that agent's pool, bound to your
wallet — and then, **automatically, with no claim step**:

- **Your reward weight is locked the moment you submit** —
  `w = 10 / (1 + 0.1 × agent_total_usage_so_far)`. Feedback at the very first
  usage locks in the maximum weight (10) *forever*; the same feedback after
  ~1,000 turns of agent usage locks in ≈0.1. Early feedback keeps its full
  value no matter how big the agent later gets.
- At each **weekly emission epoch**, the pool pays out
  `A(t) = (M_pool − M_solo) × w_k / Σ w_j` per contribution — **75% to you**,
  25% to the treasury — credited straight to your account (bound to your
  address), automatically, no claim step.
- **Double early-bird:** the pool also emits a fixed fraction of what
  *remains*, so epoch 1 pays more than epoch 10 even at equal weight. Early
  feedback × early epochs is where the real money is.
- One feedback contribution **per agent** per user — so trying all six agents
  and giving honest feedback on each stakes you in all six pools.

What good feedback looks like: a problem you actually hit, a confusing step, a
missing capability, a concrete suggestion. (Spam/duplicate feedback can be
disabled by governance and earns nothing.)

> **In short: early users don't need to keep mining — feedback given during
> the agent's first usage locks in a high weight, and the weekly payouts it
> earns can sustain (and exceed) what you spend.** Later users' feedback locks
> in a small weight — it still registers and still pays, but won't cover
> continued usage by itself; that is by design, and it's the signal to move to
> contributing or mining (Step 5).
> Note: the first weekly epoch pays out once the reward pool goes live
> (expected late June 2026); your contribution — and its frozen weight — is
> registered from the moment you submit it.

## Step 5 — Earning later, once feedback rewards have decayed

As the agents accumulate usage, new feedback locks in ever-smaller weights and
stops covering your turn costs. Keep earning by:

1. **Mining on [physicsworldmodel.org](https://physicsworldmodel.org)** — more
   principles, digital twins, benchmarks, solutions (the bootstrap path never
   closes).
2. **Weekly wins** — benchmark competitions and weekly challenge rewards on
   the site.
3. **Registered contributions used by others** — contribute a tool, solution,
   or dataset to an agent (e.g. a CASSI solver to computational-imaging);
   every paid turn that *uses* it adds usage-weight, and you earn from that
   agent's pool every week it keeps being used. This is the long-term track —
   usage-weighted, not first-come.
4. **Compute provision** — serve GPU jobs for the compute loop and earn the
   provider side of the 90/10 split.

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
