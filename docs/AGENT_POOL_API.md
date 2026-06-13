# Agent-Pool API — server-side spec (feedback + usage mining)

This is the contract the **ai4science CLI** already speaks (as of v0.5.18). It
documents exactly what the client sends/expects so the **physicsworldmodel.org**
side can match it. The focus is the **feedback-to-earn** endpoint (the zero-login
path from client change #2); the supporting endpoints are listed for context.

All paths are under `https://physicsworldmodel.org` (or the mirror in
`MIRROR.url`). All bodies are JSON; all responses are JSON. The client treats any
status `>= 400` as a failure and surfaces `http <code>`; `200` is parsed.

Identity comes in two forms:
- **Account token** — `Authorization: Bearer pwm_…` (from `ai4science login --pwm`,
  a revocable API key). Present whenever the user is logged in.
- **Local wallet** — a `wallet` field in the body (a `0x…` off-chain address from
  `ai4science login --wallet` / auto-provisioned). Present **only on the
  zero-login path**, when there is no token.

---

## 1. `POST /api/v1/agent-pool/{agent_name}/feedback` — feedback-to-earn

`{agent_name}` is one of the registered agents: `claude-code`, `codex`,
`unified-LLM`, `research`, `paper`, `computational-imaging`, …

### Request

**Headers** (one of):
```
Authorization: Bearer pwm_…        # logged-in path
(no Authorization header)          # zero-login path
```

**Body:**
```jsonc
{
  "text": "the search is fast but the input box should be wider",  // required
  "wallet": "0xabc…def"   // present ONLY when there is no token (zero-login)
}
```

### Response `200`
```jsonc
{
  "status": "accepted",     // see enum below — REQUIRED
  "reward": 0.5,            // PWM credited this call (number) — when accepted
  "covers_turns": 12        // how many more agent turns this sustains — optional
}
```

The client renders an accepted reward as:
`accepted — earned 0.5 PWM (sustains ~12 more turns)`.

### `status` enum (the client recognizes these exactly)
| `status` | Meaning | Client shows |
|---|---|---|
| `accepted` | feedback counted, reward credited | `accepted — earned N PWM (sustains ~K more turns)` |
| `use_agent_first` | user hasn't used this agent enough yet | the raw status |
| `need_more_usage` | more metered usage required before another reward | the raw status |
| `balance_not_low` | runway not low enough to refill yet (sustenance model) | the raw status |
| `program_full` | early-user first-N cap reached for this agent | `program full (first-N guard)` |
| anything else (200) | passed through | the raw status |
| HTTP `>= 400` | hard error | `http <code>` |

> Return `200` with one of the soft statuses above for *expected* refusals
> (not-eligible-yet). Reserve `4xx` for malformed requests / auth failures /
> unknown agent. A `4xx` shows the user a scary `http 4xx`.

### Reward model (recommended — matches the client's copy)
The CLI tells users feedback *"refills a shrinking runway: ~19 turns, then 18, …
floor 5; early feedback refills the most."* Implement per-(identity, agent):
- Reward = PWM equivalent of a **decreasing** turn-runway: 19 turns → 18 → 17 →
  … → **floor 5 turns**. First feedback pays most; later ones taper.
- `covers_turns` = the runway granted this time (so the client can show it).
- Convert turns→PWM using the agent's metered avg PWM/turn.

### Zero-login (`wallet`) semantics — **the part to build for #2**
When there is **no `Authorization`** and a `wallet` is present:
1. **Resolve/create** an off-chain ledger account keyed by that wallet address
   (Phase-1: off-chain balance only; the address is not yet an on-chain ECDSA
   key, so don't expect a signature).
2. Apply the **same eligibility + reward** logic as the token path, but scoped to
   that wallet.
3. **Credit the reward to that wallet's off-chain balance.**
4. Until this is built, the endpoint will reject the no-token call (401/4xx) and
   the user sees `failed (http 4xx)` — so gate this behind a feature flag and
   ship the two paths together.

### Anti-abuse (REQUIRED before opening the zero-login path)
A local wallet is free to mint infinitely, so treat unauthenticated feedback as
**low-trust**:
- **Proof-of-usage:** only reward a wallet/account that has **metered usage** on
  this agent (see §2). No usage → `use_agent_first`. This is the primary gate.
- **Rate-limit** per (wallet, agent): e.g. ≤ 1 rewarded feedback per N metered
  turns, and a hard daily cap. Excess → `need_more_usage`.
- **Per-IP / per-device** ceiling on *new* wallets and on total feedback reward,
  to blunt Sybil farms.
- **First-N cap** per agent (`program_full`) so a pool can't be drained on day one.
- **Content sanity:** length bounds, dedupe near-identical text per wallet,
  optional spam/LLM-quality filter; low-quality → soft refuse (200, not reward).
- **Idempotency:** dedupe retries (e.g. hash of `(wallet|token, agent, text,
  minute-bucket)`).

> Token-authenticated feedback is higher-trust (revocable account behind it) and
> can use looser limits than the wallet path.

---

## 2. `POST /api/v1/agent-pool/usage` — usage mining (the primary earn signal)

Fire-and-forget; the client never blocks on it. Sent once per paid turn for each
**registered** (non-base) tool the turn used. **Auth: Bearer token only** (sent
only when the gate is enabled).

**Body:**
```jsonc
{
  "contribution_id": "compute_dispatch",  // the registered tool/contribution used
  "agent_name": "computational-imaging",
  "turn_id": "<session>:<n>",             // idempotency key
  "weight_units": 1.0
}
```
- **Idempotent** per `(contribution_id, turn_id)` — the client may retry.
- This is the usage-weighted emission signal that funds the per-agent pools
  (largest = computational-imaging). Feedback (§1) is the *complement*; this is
  the main meter.

---

## 3. Supporting endpoints (already live for the token path)

### `GET /api/v1/pwm-token/balance`
Auth: Bearer token. → `{ "balance": <number> }`. The gate blocks a turn when
`balance <= min_balance`.

### `POST /api/v1/pwm-token/spend`
Auth: Bearer token. Atomic, idempotent debit of metered per-turn PWM.
```jsonc
{ "amount": 0.013, "purpose": "ai4science:claude-code:claude-opus-4-8",
  "provider_wallet": "0x…", "idempotency_key": "<session>:<n>" }
```
- `402` → insufficient balance (client shows "balance exhausted").
- `idempotency_key` is `(session, turn)`; duplicates must be no-ops.

### Device-flow login (for reference)
`POST /api/v1/cli-auth/start` → `{ device_code, user_code, verification_uri }`;
`POST /api/v1/cli-auth/poll` → `{ status, token, base, email, wallet, user_id }`.
The CLI stores `{token, base, email, wallet, user_id}` and reuses the token
everywhere. `DELETE /api/v1/auth/api-key` revokes.

---

## 4. Minimal server checklist for change #2
- [ ] `POST /agent-pool/{agent}/feedback` accepts **no-auth + `wallet`** body.
- [ ] Off-chain account auto-created/keyed by wallet address.
- [ ] Eligibility reuses the **usage meter** (§2) → `use_agent_first` /
      `need_more_usage` when thin.
- [ ] Shrinking-runway reward (19→…→5 turns) returning `{status, reward,
      covers_turns}`.
- [ ] Rate-limit per wallet + per IP/device; `program_full` first-N cap.
- [ ] Soft refusals are `200 {status:…}`, hard errors are `4xx`.
- [ ] Idempotency on retried feedback.

Client status: **ready** (ai4science ≥ v0.5.18). Logged-in path works against the
existing token auth today; the wallet path waits on the bullets above.
