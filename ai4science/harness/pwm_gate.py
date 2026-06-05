from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Optional, Tuple

_EARN = ("Earn PWM by submitting verified principles, specs, benchmarks, or solutions "
         "(physicsworldmodel.org) — every AI4Science turn costs PWM.")


def _truthy(v) -> bool:
    return str(v or "").strip().lower() in ("1", "true", "yes", "on")


class PwmGate:
    """Gate the agent on the user's earned PWM balance (off-chain ledger).

    check() blocks a turn when balance <= min_balance; charge() debits the metered
    per-turn PWM to the provider wallet via /spend. Disabled unless AI4SCIENCE_PWM_GATE
    is set AND a pwm_ token is present (so dev/CI run free)."""

    def __init__(self, *, token: Optional[str], base: str, enabled: bool,
                 min_balance: float = 0.0):
        self.token = token
        self.base = (base or "").rstrip("/")
        self.enabled = enabled
        self.min_balance = min_balance

    def _get(self, path: str) -> dict:
        req = urllib.request.Request(self.base + path, method="GET", headers={
            "Authorization": f"Bearer {self.token}", "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))

    def _post(self, path: str, body: dict):
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(self.base + path, data=data, method="POST", headers={
            "Authorization": f"Bearer {self.token}", "Content-Type": "application/json",
            "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.status, json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read().decode("utf-8"))
            except Exception:
                return e.code, {}

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

    @classmethod
    def from_env(cls) -> "PwmGate":
        token = os.environ.get("PWM_TOKEN") or os.environ.get("PWM_ONBOARD_TOKEN")
        base = (os.environ.get("PWM_BASE") or os.environ.get("PWM_ONBOARD_BASE")
                or "https://physicsworldmodel.org")
        enabled = _truthy(os.environ.get("AI4SCIENCE_PWM_GATE")) and bool(token)
        return cls(token=token, base=base, enabled=enabled)
