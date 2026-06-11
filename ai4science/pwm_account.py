"""physicsworldmodel.org ACCOUNT login for the CLI (device flow; token only).

`ai4science login --pwm` runs an RFC 8628-style device flow: the CLI shows a
short code, the user approves it in their browser while logged in (SIWE or
password), and the CLI receives the account's revocable ``pwm_`` API key.

What is stored here is ONLY that token — NEVER a wallet private key, never a
password. The token spends the website ledger balance (no on-chain signing
power) and is revocable any time (Account → API key, or DELETE
/api/v1/auth/api-key). PwmGate uses this as the default token source when
PWM_TOKEN isn't set, so logging in once replaces exporting PWM_TOKEN by hand.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable, Optional

DEFAULT_BASE = "https://physicsworldmodel.org"
# When the primary is blocked (institutional filters: "PersonalWebSites"
# category etc.), the CLI auto-falls-back to the mirror published here —
# GitHub is reachable on networks that block the primary.
MIRROR_POINTER = ("https://raw.githubusercontent.com/integritynoble/"
                  "AI4Science/main/MIRROR.url")


def fetch_mirror() -> Optional[str]:
    """Current mirror base from the GitHub pointer file, or None."""
    try:
        import httpx
        r = httpx.get(MIRROR_POINTER, timeout=10)
        if r.status_code == 200:
            url = r.text.strip().splitlines()[0].strip()
            if url.startswith("https://"):
                return url.rstrip("/")
    except Exception:
        pass
    return None


def _path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return Path(os.environ.get("AI4SCIENCE_PWM_ACCOUNT",
                               base / "ai4science" / "pwm_account.json"))


def load() -> Optional[dict]:
    """The stored account ({base, token, email, wallet, user_id}) or None."""
    try:
        d = json.loads(_path().read_text())
        return d if d.get("token") else None
    except Exception:
        return None


def save(*, base: str, token: str, email: Optional[str] = None,
         wallet: Optional[str] = None, user_id: Optional[int] = None) -> Path:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "base": base.rstrip("/"), "token": token, "email": email,
        "wallet": wallet, "user_id": user_id,
        "note": "revocable pwm_ API key — never a wallet private key",
    }, indent=2) + "\n")
    os.chmod(p, 0o600)
    return p


def clear() -> bool:
    p = _path()
    if p.exists():
        p.unlink()
        return True
    return False


def login_device_flow(base: str = DEFAULT_BASE, *,
                      echo: Callable[[str], None] = print,
                      sleeper: Callable[[float], None] = time.sleep,
                      open_browser: bool = True) -> dict:
    """Run the device flow against `base` and persist the issued token.

    Returns the saved account dict. Raises RuntimeError on deny/expiry.
    """
    import httpx

    base = base.rstrip("/")

    def _start(b):
        r = httpx.post(f"{b}/api/v1/cli-auth/start",
                       json={"client": "ai4science-cli"}, timeout=15)
        r.raise_for_status()
        return r.json()

    try:
        d = _start(base)
    except Exception as e:
        if base != DEFAULT_BASE.rstrip("/"):
            raise            # explicit --base: don't second-guess the user
        # Primary blocked/unreachable (e.g. an institutional category filter
        # returning 403) — try the published mirror automatically.
        echo(f"[login] {base} unreachable ({type(e).__name__}: "
             f"{str(e)[:80]}) — checking for a mirror…")
        mirror = fetch_mirror()
        if not mirror:
            echo("[login] no mirror published. Fixes: ask IT to whitelist "
                 "physicsworldmodel.org, or pass --base <mirror-url>. "
                 "See the manual's blocked-network section.")
            raise
        echo(f"[login] using mirror: {mirror}")
        base = mirror
        d = _start(base)
    url, code = d["verification_url"], d["user_code"]
    echo(f"\nTo log in, open:\n\n    {url}\n")
    echo(f"and approve the code:  {code}")
    echo("(this issues a revocable API key — your wallet private key is never involved)\n")
    if open_browser:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass

    interval = float(d.get("interval", 3))
    deadline = time.time() + float(d.get("expires_in", 600))
    while time.time() < deadline:
        sleeper(interval)
        try:
            p = httpx.post(f"{base}/api/v1/cli-auth/poll",
                           json={"device_code": d["device_code"]}, timeout=15).json()
        except Exception:
            continue            # transient network blip — keep polling
        status = p.get("status")
        if status == "pending":
            continue
        if status == "approved":
            save(base=base, token=p["token"], email=p.get("email"),
                 wallet=p.get("wallet"), user_id=p.get("user_id"))
            return load() or {}
        if status == "denied":
            raise RuntimeError("login denied in the browser")
        raise RuntimeError("login request expired — run `ai4science login --pwm` again")
    raise RuntimeError("login timed out — run `ai4science login --pwm` again")
