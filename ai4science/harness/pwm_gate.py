from __future__ import annotations

import os
from typing import Optional, Tuple

from ai4science import wallet  # shared PWM billing transport (linked mode)

_EARN = ("Earn PWM two ways: (1) Mine on physicsworldmodel.org (principles, digital "
         "twins, benchmarks, solutions) to bootstrap your first balance. (2) IMPROVE "
         "THE AGENTS — use them until your PWM runs low, then /feedback problems + "
         "suggestions (refills a shrinking runway: ~19 turns, then 18, … floor 5; "
         "early feedback refills the most) — or contribute tools/solutions others "
         "use; the agent pools (4M PWM) pay weekly for those.")


def _truthy(v) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


# Base Claude-Code tools are platform infra, not minable contributions — usage
# logging skips them (only domain/capability tools can be registered contributions).
BASE_TOOLS = frozenset({"read", "write", "edit", "grep", "glob", "bash", "task", "ls"})


class PwmGate:
    """Gate the agent on the user's earned PWM balance (off-chain ledger).

    check() blocks a turn when balance <= min_balance; charge() debits the metered
    per-turn PWM to the provider wallet via /spend. On automatically once a pwm_
    token is remembered (logged in); AI4SCIENCE_PWM_GATE=0 opts out, no token runs
    free (dev/CI)."""

    def __init__(self, *, token: Optional[str], base: str, enabled: bool,
                 min_balance: float = 0.0):
        self.token = token
        self.base = (base or "").rstrip("/")
        self.enabled = enabled
        self.min_balance = min_balance

    def _get(self, path: str) -> dict:
        # Route through the shared wallet transport (single billing client).
        _status, data = wallet.http_get(self.base, path, self.token)
        return data

    def _post(self, path: str, body: dict):
        # Route through the shared wallet transport (single billing client).
        return wallet.http_post(self.base, path, self.token, body)

    def _get_balance(self) -> Optional[float]:
        try:
            d = self._get("/api/v1/pwm-token/balance")
            b = d.get("balance")
            return float(b) if b is not None else None
        except Exception:
            return None

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

    def post_usage(self, *, contribution_id: str, agent_name: str, turn_id: str,
                   weight_units: float = 1.0) -> bool:
        """Record that this paid turn used a registered contribution (agent-mining
        usage logging). No-op when the gate is off; fire-and-forget — a failure
        never breaks the turn. Idempotent on the backend per (contribution, turn)."""
        if not self.enabled or not contribution_id:
            return False
        try:
            status, _ = self._post("/api/v1/agent-pool/usage", {
                "contribution_id": contribution_id,
                "agent_name": agent_name,
                "turn_id": turn_id,
                "weight_units": float(weight_units),
            })
            return status < 400
        except Exception:
            return False

    def post_feedback(self, *, agent_name: str, text: str) -> Tuple[bool, str]:
        """Submit early-user feedback for an agent (agent-mining E3).

        Zero-login by design: with a logged-in account the token is the
        identity; WITHOUT one, auto-provision a local off-chain wallet
        (`wallet.ensure`) and submit identified by its address, so users earn
        without logging in. Returns (ok, status). (Server must accept
        wallet-attributed feedback for the no-login path to actually pay out.)"""
        body: dict = {"text": text}
        if not self.token:
            try:
                body["wallet"] = wallet.address()   # ensures + returns local addr
            except Exception:
                pass
        try:
            status, data = self._post(f"/api/v1/agent-pool/{agent_name}/feedback",
                                      body)
            if status >= 400:
                return False, f"http {status}"
            d = data or {}
            if d.get("status") == "accepted" and d.get("reward") is not None:
                return True, (f"accepted — earned {d['reward']:g} PWM "
                              f"(sustains ~{d.get('covers_turns')} more turns)")
            return True, d.get("status", "ok")
        except Exception as exc:
            return False, f"{type(exc).__name__}"

    @classmethod
    def from_env(cls) -> "PwmGate":
        token = os.environ.get("PWM_TOKEN") or os.environ.get("PWM_ONBOARD_TOKEN")
        base = os.environ.get("PWM_BASE") or os.environ.get("PWM_ONBOARD_BASE")
        if not token:
            # `ai4science login --pwm` stored account (revocable pwm_ API key —
            # never a wallet private key). Env vars always win for CI/scripts.
            try:
                from ai4science import pwm_account
                acct = pwm_account.load() or {}
                token = acct.get("token")
                base = base or acct.get("base")
            except Exception:
                pass
        base = base or "https://physicsworldmodel.org"
        # On automatically once an identity is remembered (logged in / PWM_TOKEN):
        # logging in is all it takes to earn + spend PWM. AI4SCIENCE_PWM_GATE=0
        # (false/no/off) is the explicit opt-out; no token → always off so
        # dev/CI run free.
        _g = os.environ.get("AI4SCIENCE_PWM_GATE")
        explicit_off = _g is not None and not _truthy(_g)
        enabled = bool(token) and not explicit_off
        return cls(token=token, base=base, enabled=enabled)
