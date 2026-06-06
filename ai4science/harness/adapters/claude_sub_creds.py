"""Claude Code subscription credentials for the anthropic backend.

The `claude` CLI (Claude Code) stores an OAuth login at
``~/.claude/.credentials.json`` (key ``claudeAiOauth``). That access token
carries the ``user:inference`` scope, so — with the ``anthropic-beta:
oauth-2025-04-20`` header — it authenticates the Messages API directly, no
``ANTHROPIC_API_KEY`` required. This is what `--auth subscription` on the
founder anthropic provider is meant to use.

Token read FRESH each call so the `claude` CLI's background refresh is picked
up. expiresAt is epoch MILLISECONDS.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Optional


def _creds_path() -> Path:
    override = os.environ.get("CLAUDE_CREDENTIALS")
    if override:
        return Path(override)
    return Path.home() / ".claude" / ".credentials.json"


def _oauth() -> dict:
    try:
        d = json.loads(_creds_path().read_text(encoding="utf-8"))
    except Exception:
        return {}
    return d.get("claudeAiOauth") or {}


def subscription_token() -> Optional[str]:
    """Fresh Claude Code subscription access token, or None."""
    return _oauth().get("accessToken") or None


def subscription_available() -> bool:
    """True when a non-expired Claude Code subscription login exists."""
    o = _oauth()
    tok = o.get("accessToken")
    if not tok:
        return False
    exp = o.get("expiresAt")  # epoch milliseconds
    if isinstance(exp, (int, float)) and exp > 0:
        return (exp / 1000.0) > time.time()
    return True
