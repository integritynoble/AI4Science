"""PWM wallet (point 6) — local off-chain account OR platform-linked ledger.

This module is the single PWM billing client for AI4Science. The harness usage
gate (ai4science/harness/pwm_gate.py) routes its balance/spend through the shared
transport here, so there is one place that knows the platform endpoints.

Two billing modes (env `AI4SCIENCE_BILLING`, or auto-detected):

  local     — self-contained file wallet at ~/.config/ai4science/wallet.json
              (chmod 600). Credited/debited locally. Offline/dev/tests.
              (default when no PWM token is set)

  platform  — LINKED MODE: the canonical balance lives on the platform reward
              ledger (`pwm_token_account`, physicsworldmodel.org). `balance()`
              reads it (GET /api/v1/pwm-token/balance) and `debit()` posts an
              atomic, idempotent spend (POST /api/v1/pwm-token/spend). This closes
              the earn->spend loop: PWM earned via the onboarding portal becomes
              spendable in AI4Science. (default when a PWM token IS set)

Config (platform mode):
  PWM_TOKEN / PWM_ONBOARD_TOKEN / AI4SCIENCE_PWM_TOKEN   per-user bearer token
  PWM_BASE  / PWM_ONBOARD_BASE  / AI4SCIENCE_PWM_API      API base (default https://physicsworldmodel.org)
  AI4SCIENCE_BILLING                                      force "platform" or "local"

On-chain key signing / withdrawal is a later phase (relay M1 + bridge M6); this
layer is off-chain accounting only and never moves on-chain tokens.
"""
from __future__ import annotations

import json
import os
import secrets
import stat
import urllib.error
import urllib.request
from pathlib import Path
from typing import Dict, Optional, Tuple

DEFAULT_BASE = "https://physicsworldmodel.org"
BALANCE_PATH = "/api/v1/pwm-token/balance"
SPEND_PATH = "/api/v1/pwm-token/spend"


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

def platform_token() -> Optional[str]:
    return (os.environ.get("AI4SCIENCE_PWM_TOKEN")
            or os.environ.get("PWM_TOKEN")
            or os.environ.get("PWM_ONBOARD_TOKEN"))


def platform_base() -> str:
    base = (os.environ.get("AI4SCIENCE_PWM_API")
            or os.environ.get("PWM_BASE")
            or os.environ.get("PWM_ONBOARD_BASE")
            or DEFAULT_BASE)
    return base.rstrip("/")


def billing_mode() -> str:
    """'platform' (linked) or 'local' (file). Explicit env wins; else auto:
    platform iff a PWM token is configured."""
    m = os.environ.get("AI4SCIENCE_BILLING", "").strip().lower()
    if m in ("platform", "local"):
        return m
    return "platform" if platform_token() else "local"


def _require_token() -> str:
    t = platform_token()
    if not t:
        raise BillingAuthError(
            "no PWM token — set PWM_TOKEN to your physicsworldmodel.org key "
            "(required for platform billing)."
        )
    return t


# ───────────── shared HTTP transport (used by wallet AND PwmGate) ─────────────

def _http_request_httpx(method: str, url: str, token: Optional[str],
                        body: Optional[dict]) -> Tuple[int, dict]:
    """httpx-based transport (prefers bundled certifi over OS cert store —
    avoids Windows SSL store gaps that affect urllib). Only called when httpx
    is installed (it's a hard dep via pwm_account → login flow)."""
    import httpx
    headers: dict = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = httpx.request(method, url, json=body, headers=headers, timeout=30)
        try:
            data = resp.json()
        except Exception:
            data = {}
        return resp.status_code, (data if isinstance(data, dict) else {})
    except httpx.HTTPStatusError as e:
        try:
            data = e.response.json()
        except Exception:
            data = {}
        return e.response.status_code, (data if isinstance(data, dict) else {})
    except httpx.RequestError as e:
        raise BillingError(f"PWM billing API unreachable at {url}: {e}") from e


def http_request(method: str, base: str, path: str, token: Optional[str],
                 body: Optional[dict] = None) -> Tuple[int, dict]:
    """Single HTTP entry point for all PWM billing calls. Returns
    (status_code, parsed_json). HTTP error *statuses* are returned (not raised)
    so callers can branch on 402/401; only true unreachability raises.

    Prefers httpx (bundled certifi, works on Windows) over urllib when available."""
    url = base.rstrip("/") + path
    try:
        return _http_request_httpx(method, url, token, body)
    except ImportError:
        pass  # httpx not installed — fall through to urllib

    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, {}
    except urllib.error.URLError as e:
        raise BillingError(f"PWM billing API unreachable at {url}: {e}") from e


def http_get(base: str, path: str, token: Optional[str]) -> Tuple[int, dict]:
    return http_request("GET", base, path, token)


def http_post(base: str, path: str, token: Optional[str], body: dict) -> Tuple[int, dict]:
    return http_request("POST", base, path, token, body)


# ───────────────────────────── platform-linked balance/spend ─────────────────────────────

def _platform_balance() -> float:
    status, j = http_get(platform_base(), BALANCE_PATH, _require_token())
    if status == 401:
        raise BillingAuthError("PWM token rejected (401)")
    if status != 200:
        raise BillingError(f"balance check failed ({status}): {j}")
    b = j.get("balance")
    if b is None:
        raise BillingError(f"balance response missing 'balance': {j}")
    return round(float(b), 6)


def _platform_debit(amount: float, *, idempotency_key: Optional[str],
                    provider_wallet: Optional[str], purpose: Optional[str]) -> float:
    if not idempotency_key:
        raise ValueError("platform debit requires an idempotency_key (the op id)")
    if not provider_wallet:
        raise ValueError("platform debit requires provider_wallet (who earns the PWM)")
    status, j = http_post(platform_base(), SPEND_PATH, _require_token(), {
        "amount": round(float(amount), 6),
        "purpose": purpose or "ai4science",
        "provider_wallet": provider_wallet,
        "idempotency_key": idempotency_key,
    })
    if status == 401:
        raise BillingAuthError("PWM token rejected (401)")
    if status == 402:
        raise InsufficientPWM(j.get("needed", amount),
                              j.get("balance", j.get("balance_after", 0.0)))
    if status >= 400 or (isinstance(j, dict) and j.get("success") is False):
        raise BillingError(f"spend failed ({status}): {j}")
    ba = j.get("balance_after")
    return round(float(ba), 6) if ba is not None else _platform_balance()


# ───────────────────────────── local file wallet ─────────────────────────────

def wallet_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return Path(os.environ.get("AI4SCIENCE_WALLET", base / "ai4science" / "wallet.json"))


def _new_address() -> str:
    """A 0x + 40-hex local address. (Phase 1: random, not an ECDSA account.)"""
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
    """Local wallet address (display / back-compat). In platform mode, account
    identity is the platform token."""
    return ensure()["address"]


def balance() -> float:
    """Spendable PWM balance — platform ledger (platform mode) or local file."""
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
          provider_wallet: Optional[str] = None, purpose: Optional[str] = None,
          reason: Optional[str] = None, meta: Optional[dict] = None) -> float:
    """Spend PWM, returning the new balance. Raises InsufficientPWM if short.

    platform mode: POST /api/v1/pwm-token/spend (atomic, idempotent); requires
      `idempotency_key` (the billable op id) and `provider_wallet` (who earns).
      `purpose` labels the spend (`reason` accepted as an alias).
    local mode: deducts from the local file (kwargs ignored)."""
    if amount < 0:
        raise ValueError("debit must be non-negative")
    if billing_mode() == "platform":
        return _platform_debit(amount, idempotency_key=idempotency_key,
                               provider_wallet=provider_wallet,
                               purpose=purpose or reason)
    return _local_debit(amount)
