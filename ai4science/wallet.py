"""PWM wallet (point 6) — local off-chain account OR platform-linked ledger.

Two billing modes (env `AI4SCIENCE_BILLING`, or auto-detected):

  local     — the original self-contained file wallet at
              ~/.config/ai4science/wallet.json (chmod 600). Credited/debited
              locally. For offline/dev/tests. (default when no token is set)

  platform  — LINKED MODE: the canonical balance lives on the platform reward
              ledger (`pwm_token_account`, physicsworldmodel.org). `balance()`
              reads it and `debit()` posts an atomic, idempotent charge via the
              billing API (see pwm-team/plan/easy_onboarding/ledger_link_spec.md).
              This closes the earn->spend loop: PWM earned via the onboarding
              portal becomes spendable in AI4Science. (default when a token IS set)

Config (platform mode):
  AI4SCIENCE_PWM_TOKEN   per-user bearer token from the platform account
  AI4SCIENCE_PWM_API     billing API base (default https://physicsworldmodel.org/pwm/v1)
  AI4SCIENCE_BILLING     force "platform" or "local" (overrides auto-detect)

Real on-chain key signing / withdrawal is a later phase (relay M1 + bridge M6);
this layer is off-chain accounting only and never moves on-chain tokens.
"""
from __future__ import annotations

import json
import os
import secrets
import stat
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

DEFAULT_API = "https://physicsworldmodel.org/pwm/v1"


# ───────────────────────────── errors ─────────────────────────────

class BillingError(RuntimeError):
    """Billing/ledger call failed (network, server, auth)."""


class BillingAuthError(BillingError):
    """The PWM token is missing or rejected."""


class InsufficientPWM(BillingError, ValueError):
    """Balance is below the amount required for the operation.

    Subclasses ValueError too, so callers/tests written against the original
    `debit()` (which raised ValueError on insufficient funds) keep working."""

    def __init__(self, needed: float, balance: float):
        self.needed = needed
        self.balance = balance
        super().__init__(f"insufficient PWM: need {needed}, have {balance}")


# ───────────────────────────── mode / config ─────────────────────────────

def billing_mode() -> str:
    """'platform' (linked) or 'local' (file). Explicit env wins; else auto:
    platform iff a PWM token is configured."""
    m = os.environ.get("AI4SCIENCE_BILLING", "").strip().lower()
    if m in ("platform", "local"):
        return m
    return "platform" if os.environ.get("AI4SCIENCE_PWM_TOKEN") else "local"


def _api_base() -> str:
    return os.environ.get("AI4SCIENCE_PWM_API", DEFAULT_API).rstrip("/")


def _token() -> str:
    t = os.environ.get("AI4SCIENCE_PWM_TOKEN")
    if not t:
        raise BillingAuthError(
            "AI4SCIENCE_PWM_TOKEN not set — required for platform billing. "
            "Get a token from your physicsworldmodel.org account."
        )
    return t


# ───────────────────────────── HTTP seam (monkeypatched in tests) ─────────────────────────────

def _request(method: str, path: str, token: str, body: Optional[dict] = None) -> Tuple[int, dict]:
    """Single HTTP entry point. Returns (status_code, parsed_json). Raises
    BillingError only when the API is unreachable (HTTP error statuses are
    returned, not raised, so callers can branch on 402/401)."""
    url = _api_base() + path
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8") or "{}"
            return resp.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        try:
            payload = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            payload = {}
        return e.code, payload
    except urllib.error.URLError as e:  # unreachable / DNS / timeout
        raise BillingError(f"PWM billing API unreachable at {url}: {e}") from e


# ───────────────────────────── platform-linked balance/charge ─────────────────────────────

def _platform_balance() -> float:
    code, j = _request("GET", "/balance", _token())
    if code == 401:
        raise BillingAuthError("PWM token rejected (401)")
    if code != 200:
        raise BillingError(f"balance check failed ({code}): {j}")
    return round(float(j.get("pwm", 0.0)), 6)


def _platform_debit(amount: float, *, idempotency_key: Optional[str],
                    provider_wallet: Optional[str], reason: Optional[str],
                    meta: Optional[dict]) -> float:
    if not idempotency_key:
        raise ValueError("platform debit requires an idempotency_key (the op id)")
    if not provider_wallet:
        raise ValueError("platform debit requires provider_wallet (who earns the PWM)")
    body = {
        "idempotency_key": idempotency_key,
        "amount_pwm": round(float(amount), 6),
        "provider_wallet": provider_wallet,
        "reason": reason or "ai4science",
        "meta": meta or {},
    }
    code, j = _request("POST", "/charge", _token(), body)
    if code == 401:
        raise BillingAuthError("PWM token rejected (401)")
    if code == 402 or (isinstance(j, dict) and j.get("charged") is False):
        raise InsufficientPWM(j.get("needed", amount), j.get("balance", 0.0))
    if code != 200 or not (isinstance(j, dict) and j.get("charged")):
        raise BillingError(f"charge failed ({code}): {j}")
    return round(float(j.get("new_balance", 0.0)), 6)


# ───────────────────────────── local file wallet ─────────────────────────────

def wallet_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return Path(os.environ.get("AI4SCIENCE_WALLET", base / "ai4science" / "wallet.json"))


def _new_address() -> str:
    """A 0x + 40-hex local address. (Phase 1: random, not an ECDSA account —
    on-chain key derivation comes with the settlement layer.)"""
    return "0x" + secrets.token_hex(20)


def _save(w: Dict) -> None:
    p = wallet_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(w, indent=2) + "\n", encoding="utf-8")
    try:
        os.chmod(p, stat.S_IRUSR | stat.S_IWUSR)   # 600 — it's a wallet
    except OSError:
        pass


def load() -> Optional[Dict]:
    p = wallet_path()
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def ensure() -> Dict:
    """Return the local wallet, creating one (address, 0 balance) if absent."""
    w = load()
    if w is None:
        w = {"address": _new_address(), "balance_pwm": 0.0, "phase": "offchain-v1"}
        _save(w)
    return w


def _local_balance() -> float:
    return round(float(ensure().get("balance_pwm", 0.0)), 6)


def _local_credit(amount: float) -> float:
    if amount < 0:
        raise ValueError("credit must be non-negative")
    w = ensure()
    w["balance_pwm"] = round(float(w.get("balance_pwm", 0.0)) + amount, 6)
    _save(w)
    return w["balance_pwm"]


def _local_debit(amount: float) -> float:
    w = ensure()
    bal = float(w.get("balance_pwm", 0.0))
    if amount > bal:
        raise InsufficientPWM(round(amount, 6), round(bal, 6))
    w["balance_pwm"] = round(bal - amount, 6)
    _save(w)
    return w["balance_pwm"]


# ───────────────────────────── public API (mode dispatch) ─────────────────────────────

def mode() -> str:
    """Current billing mode: 'platform' or 'local'."""
    return billing_mode()


def address() -> str:
    """Local wallet address. In platform mode, account identity is the platform
    token; the local address is still returned for display/back-compat."""
    return ensure()["address"]


def balance() -> float:
    """Spendable PWM balance — from the platform ledger (platform mode) or the
    local file (local mode)."""
    return _platform_balance() if billing_mode() == "platform" else _local_balance()


def credit(amount: float) -> float:
    """Local-mode only. In platform mode, PWM is credited by the platform reward
    ledger (earned via the onboarding portal), never by the client."""
    if billing_mode() == "platform":
        raise BillingError(
            "credits are issued by the platform reward ledger, not the client — "
            "earn PWM via the onboarding portal (/submit)"
        )
    return _local_credit(amount)


def debit(amount: float, *, idempotency_key: Optional[str] = None,
          provider_wallet: Optional[str] = None, reason: Optional[str] = None,
          meta: Optional[dict] = None) -> float:
    """Spend PWM, returning the new balance. Raises InsufficientPWM if short.

    platform mode: posts an atomic, idempotent charge to the platform ledger;
      requires `idempotency_key` (the billable op id) and `provider_wallet`
      (who earns the PWM, e.g. the paper-fn provider).
    local mode: deducts from the local file (kwargs ignored)."""
    if amount < 0:
        raise ValueError("debit must be non-negative")
    if billing_mode() == "platform":
        return _platform_debit(amount, idempotency_key=idempotency_key,
                               provider_wallet=provider_wallet, reason=reason, meta=meta)
    return _local_debit(amount)
