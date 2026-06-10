# Test all six agents with ONE wallet

This is the operate-it-yourself guide for testing every agent (unified-LLM,
research, paper, claude-code, codex, computational-imaging) with a **single
wallet** — showing the wallet both **pays PWM to run** each agent and **earns
PWM** from each agent's pool.

## Test wallet

```
0x7E57000000000000000000000000000000000001        (0x7E57 = "TEST")
```

Use this, or substitute your own `0x…` wallet anywhere it appears.

---

## A. One command (recommended)

On a box that has the founder LLM providers configured (Claude/ChatGPT
subscriptions, etc. — e.g. the agent host):

```bash
cd <AI4Science repo>
scripts/test_agents_mining.sh 0x7E57000000000000000000000000000000000001
#   (omit the arg to use the default test wallet)
```

It spins up the real backend on SQLite, provisions one wallet-bound account,
funds it 100 PWM, runs a gated turn + `/feedback` on all six agents, emits one
weekly epoch, prints the result, and cleans up.

**Against an existing staging/remote backend** (skip the local server — needs an
admin token for the admin ops):

```bash
scripts/test_agents_mining.sh 0x7E57…0001 \
  --backend https://staging.example \
  --admin-token <admin key/JWT>      # or env PWM_ADMIN_TOKEN
```

**Expected output (either mode):**

```
   unified-LLM            charged -0.043   feedback: accepted — earned 0.0455 PWM (sustains ~19 more turns)
   research               charged -0.215   feedback: accepted — earned 0.2292 PWM (sustains ~19 more turns)
   ...
   (negative "charged" = the instant refill exceeded the turn cost — the
    sustenance loop refilling a ~19-turn runway; test mode treats any balance
    as low, prod requires a nearly-empty balance)

   feedback pays an INSTANT usage-sized reward; weekly pool epochs pay
   usage-weighted contributions (tools/solutions) only.
   wallet 0x7E57…0001  balance 100.0  lifetime_earned ≈ 100.013
```

> **Model lineup (since 2026-06-10):** anthropic-backed turns now serve
> **`claude-fable-5`** first (Opus 4.8 is the fallback — chain: Fable 5 →
> Opus 4.8 → Sonnet 4.6 → GPT-5.5 → Gemini). The charge figures above are
> from Opus 4.8 runs; Fable 5 turns bill at the same price tier and land
> within ~15% (e.g. unified-LLM ≈ 0.0025 PWM, verified live). The earnings
> table is unaffected — A_k depends on the pool config, not the model.

---

## B. Manual, step by step

So you understand each hop.

0. **Log in — the easy way (recommended).** No token copy-pasting: the device
   flow stores your account's revocable `pwm_` API key (never a private key),
   and the gate picks it up automatically:
   ```bash
   ai4science login --pwm                 # approve the short code in your browser
   ai4science whoami                      # shows your account + bound wallet
   ```
   Your browser login (SIWE wallet or password) authorizes it; the CLI stores
   only the key at `~/.config/ai4science/pwm_account.json` (0600). Verified
   live on production 2026-06-10 (see pwm repo
   `pwm-team/doc/PWM_AI4SCIENCE_LOGIN_PWM_LIVE_TEST_2026-06-10.md`).

   *Script/CI alternative* — set the token by hand (env always beats the
   stored login):
   ```bash
   export B=https://physicsworldmodel.org           # or your staging/local backend
   export WALLET=0x7E57000000000000000000000000000000000001
   export TOK=<your pwm_ key / admin JWT>            # the account bound to $WALLET
   export H="Authorization: Bearer $TOK"
   ```

1. **Bind the wallet + fund it.** Earn PWM on physicsworldmodel.org first
   (submit a principle / digital twin / benchmark / solution → auto-award), or
   have an admin award test PWM:
   ```bash
   curl -s -X POST "$B/api/v1/pwm-token/wallet"  -H "$H" -d "{\"address\":\"$WALLET\"}"
   curl -s     "$B/api/v1/pwm-token/balance"     -H "$H"      # confirm > 0
   ```
   (With `login --pwm` the wallet is already bound to your account — skip the
   bind, just confirm the balance.)

2. **Run each agent with the gate ON** (one account, just change `--mode`):
   ```bash
   export AI4SCIENCE_PWM_GATE=1           # token comes from login --pwm…
   # export PWM_BASE="$B" PWM_TOKEN="$TOK"  # …or set env explicitly (CI)
   for a in unified-LLM research paper claude-code codex computational-imaging; do
     printf 'reply DONE\n/feedback please improve %s\n' "$a" \
       | ai4science chat --mode "$a" --workspace /tmp --yes
   done
   ```
   Each turn charges PWM to the provider; `/feedback` (once your balance runs
   low after real usage) refills a shrinking runway of turns.

3. **Emit one weekly epoch** (admin) — pays your wallet from each pool:
   ```bash
   curl -s -X POST "$B/api/v1/agent-pool/run-epoch" -H "$H" -d '{}'
   ```

4. **Verify your wallet earned across all six:**
   ```bash
   curl -s "$B/api/v1/pwm-token/balance" -H "$H"                   # spend + earnings
   for a in unified-LLM research paper claude-code codex computational-imaging; do
     curl -s "$B/api/v1/agent-pool/$a/leaderboard" -H "$H"; echo
   done
   curl -s "$B/api/v1/agent-pool/settlements" -H "$H"              # on-chain (M6) export
   ```

---

## What it proves

- **One wallet/token covers all six agents** — no per-agent credentials. The
  founder providers serve the LLMs; your wallet pays PWM.
- **Pays to run:** every turn debits PWM from your wallet to the provider.
- **Earns from each agent:** `/feedback` pays an **instant usage-sized
  reward** refilling a shrinking runway (~19→5 turns, decaying with agent
  usage; unlocked only on a nearly-empty balance), and any registered
  tool/solution you author earns **75%** of
  each agent's weekly emission (treasury 25%), with **computational-imaging
  the largest pool**.

## Notes

- `claude-code` needs an Anthropic (Claude Code) login on the host; `codex` needs
  a Codex/ChatGPT login. The PWM/wallet is billing only — the founder provides
  the LLM, you pay PWM.
- The whole loop is **off by default** — it only runs when `AI4SCIENCE_PWM_GATE=1`
  and a token is present (from `ai4science login --pwm`, or `PWM_TOKEN` which
  always wins). `ai4science logout` removes the stored login token.
