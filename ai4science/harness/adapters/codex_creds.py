from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path
from typing import Optional, Tuple


def _auth_path() -> Path:
    home = os.environ.get("CODEX_HOME") or str(Path.home() / ".codex")
    return Path(home) / "auth.json"


def _read() -> Optional[dict]:
    try:
        return json.loads(_auth_path().read_text())
    except Exception:
        return None


def codex_available() -> bool:
    """True when a ChatGPT-subscription (auth_mode=chatgpt) codex login exists."""
    d = _read()
    if not d:
        return False
    t = d.get("tokens") or {}
    return bool(t.get("access_token") and t.get("account_id"))


def codex_token_expired(skew: int = 60) -> bool:
    """True when the access_token's JWT `exp` has passed (with `skew` seconds of
    leeway). A present-but-expired token routes to the codex adapter but 401s,
    silently billing 0 — callers use this to surface a clear "refresh" message
    instead. Unknown/undecodable expiry → treated as NOT expired (fail open;
    the live request is the real check)."""
    d = _read() or {}
    tok = (d.get("tokens") or {}).get("access_token") or ""
    parts = tok.split(".")
    if len(parts) < 2:
        return False
    try:
        pad = parts[1] + "=" * (-len(parts[1]) % 4)
        exp = json.loads(base64.urlsafe_b64decode(pad)).get("exp")
    except Exception:
        return False
    return bool(exp) and (time.time() + skew) >= exp


def codex_auth() -> Tuple[str, str]:
    """(access_token, account_id) read FRESH each call so the codex CLI's
    background token refresh is picked up. Raises if unavailable."""
    d = _read() or {}
    t = d.get("tokens") or {}
    tok, acct = t.get("access_token"), t.get("account_id")
    if not (tok and acct):
        raise RuntimeError("no codex/ChatGPT subscription (run `codex login`)")
    return tok, acct
