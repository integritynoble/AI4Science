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
weekly epoch, prints the result, and cleans up. **Expected output:**

```
   unified-LLM            charged 0.0022 PWM   feedback submitted
   research               charged 0.0047 PWM   feedback submitted
   paper                  charged 0.0032 PWM   feedback submitted
   claude-code            charged 0.0022 PWM   feedback submitted
   codex                  charged 6.7e-05 PWM  feedback submitted
   computational-imaging  charged 0.0051 PWM   feedback submitted

agent                     feedback A_k  → wallet 75%
unified-LLM                    24000.0       18000.0
research                       30000.0       22500.0
paper                          24000.0       18000.0
claude-code                    26000.0       19500.0
codex                          26000.0       19500.0
computational-imaging          70000.0       52500.0   ← largest pool
wallet 0x7E57…0001  lifetime_earned 150,100.00 PWM
```

---

## B. Manual, step by step

So you understand each hop. Set the backend + an admin token first:

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

2. **Run each agent with the gate ON** (one token/wallet, just change `--mode`):
   ```bash
   export AI4SCIENCE_PWM_GATE=1 PWM_BASE="$B" PWM_TOKEN="$TOK"
   for a in unified-LLM research paper claude-code codex computational-imaging; do
     printf 'reply DONE\n/feedback please improve %s\n' "$a" \
       | ai4science chat --mode "$a" --workspace /tmp --yes
   done
   ```
   Each turn charges PWM to the provider; `/feedback` registers a front-loaded
   feedback contribution for that agent, authored by your wallet.

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
- **Earns from each agent:** `/feedback` (and any registered tool/solution you
  use) earns your wallet **75%** of each agent's emission (treasury 25%), with
  **computational-imaging the largest pool**.

## Notes

- `claude-code` needs an Anthropic (Claude Code) login on the host; `codex` needs
  a Codex/ChatGPT login. The PWM/wallet is billing only — the founder provides
  the LLM, you pay PWM.
- The whole loop is **off by default** — it only runs when `AI4SCIENCE_PWM_GATE=1`
  and a `PWM_TOKEN` are set.
