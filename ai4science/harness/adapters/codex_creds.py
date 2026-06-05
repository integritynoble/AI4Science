from __future__ import annotations

import json
import os
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


def codex_auth() -> Tuple[str, str]:
    """(access_token, account_id) read FRESH each call so the codex CLI's
    background token refresh is picked up. Raises if unavailable."""
    d = _read() or {}
    t = d.get("tokens") or {}
    tok, acct = t.get("access_token"), t.get("account_id")
    if not (tok and acct):
        raise RuntimeError("no codex/ChatGPT subscription (run `codex login`)")
    return tok, acct
